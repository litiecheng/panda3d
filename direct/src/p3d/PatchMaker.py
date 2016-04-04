__all__ = ["PatchMaker"]

from direct.p3d.FileSpec import FileSpec
from direct.p3d.SeqValue import SeqValue
from panda3d.core import *
import copy

class PatchMaker:
    """ This class will operate on an existing package install
    directory, as generated by the Packager, and create patchfiles
    between versions as needed.  It is also used at runtime, to apply
    the downloaded patches. """

    class PackageVersion:
        """ A specific patch version of a package.  This is not just
        the package's "version" string; it also corresponds to the
        particular patch version, which increments independently of
        the "version". """

        def __init__(self, packageName, platform, version, hostUrl, file):
            self.packageName = packageName
            self.platform = platform
            self.version = version
            self.hostUrl = hostUrl
            self.file = file
            self.printName = None

            # The Package object that produces this version, if this
            # is the current, base, or top form, respectively.
            self.packageCurrent = None
            self.packageBase = None
            self.packageTop = None

            # A list of patchfiles that can produce this version.
            self.fromPatches = []

            # A list of patchfiles that can start from this version.
            self.toPatches = []

            # A temporary file for re-creating the archive file for
            # this version.
            self.tempFile = None

        def cleanup(self):
            if self.tempFile:
                self.tempFile.unlink()

        def getPatchChain(self, startPv, alreadyVisited = []):
            """ Returns a list of patches that, when applied in
            sequence to the indicated PackageVersion object, will
            produce this PackageVersion object.  Returns None if no
            chain can be found. """

            if self is startPv:
                # We're already here.  A zero-length patch chain is
                # therefore the answer.
                return []
            if self in alreadyVisited:
                # We've already been here; this is a loop.  Avoid
                # infinite recursion.
                return None

            alreadyVisited = alreadyVisited[:]
            alreadyVisited.append(self)

            bestPatchChain = None
            for patchfile in self.fromPatches:
                fromPv = patchfile.fromPv
                patchChain = fromPv.getPatchChain(startPv, alreadyVisited)
                if patchChain is not None:
                    # There's a path through this patchfile.
                    patchChain = patchChain + [patchfile]
                    if bestPatchChain is None or len(patchChain) < len(bestPatchChain):
                        bestPatchChain = patchChain

            # Return the shortest path found, or None if there were no
            # paths found.
            return bestPatchChain

        def getRecreateFilePlan(self, alreadyVisited = []):
            """ Returns the tuple (startFile, startPv, plan),
            describing how to recreate the archive file for this
            version.  startFile and startPv is the Filename and
            packageVersion of the file to start with, and plan is a
            list of tuples (patchfile, pv), listing the patches to
            apply in sequence, and the packageVersion object
            associated with each patch.  Returns (None, None, None) if
            there is no way to recreate this archive file.  """

            if self.tempFile:
                return (self.tempFile, self, [])

            if self in alreadyVisited:
                # We've already been here; this is a loop.  Avoid
                # infinite recursion.
                return (None, None, None)

            alreadyVisited = alreadyVisited[:]
            alreadyVisited.append(self)

            if self.packageCurrent:
                # This PackageVersion instance represents the current
                # version of some package.
                package = self.packageCurrent
                return (Filename(package.packageDir, package.compressedFilename), self, [])

            if self.packageBase:
                # This PackageVersion instance represents the base
                # (oldest) version of some package.
                package = self.packageBase
                return (Filename(package.packageDir, package.baseFile.filename  + '.pz'), self, [])

            # We'll need to re-create the file.
            bestPlan = None
            bestStartFile = None
            bestStartPv = None
            for patchfile in self.fromPatches:
                fromPv = patchfile.fromPv
                startFile, startPv, plan = fromPv.getRecreateFilePlan(alreadyVisited)
                if plan is not None:
                    # There's a path through this patchfile.
                    plan = plan + [(patchfile, self)]
                    if bestPlan is None or len(plan) < len(bestPlan):
                        bestPlan = plan
                        bestStartFile = startFile
                        bestStartPv = startPv

            # Return the shortest path found, or None if there were no
            # paths found.
            return (bestStartFile, bestStartPv, bestPlan)

        def getFile(self):
            """ Returns the Filename of the archive file associated
            with this version.  If the file doesn't actually exist on
            disk, a temporary file will be created.  Returns None if
            the file can't be recreated. """

            startFile, startPv, plan = self.getRecreateFilePlan()

            if startFile.getExtension() == 'pz':
                # If the starting file is compressed, we have to
                # decompress it first.
                assert startPv.tempFile is None
                startPv.tempFile = Filename.temporary('', 'patch_')
                if not decompressFile(startFile, startPv.tempFile):
                    # Failure trying to decompress the file.
                    return None
                startFile = startPv.tempFile

            if not plan:
                # If plan is a zero-length list, we're already
                # here--return startFile.  If plan is None, there's no
                # solution, and startFile is None.  In either case, we
                # can return startFile.
                return startFile

            # If plan is a non-empty list, we have to walk the list to
            # apply the patch plan.
            prevFile = startFile
            for patchfile, pv in plan:
                fromPv = patchfile.fromPv
                patchFilename = Filename(patchfile.package.packageDir, patchfile.file.filename)
                result = self.applyPatch(prevFile, patchFilename)
                if not result:
                    # Failure trying to re-create the file.
                    return None

                pv.tempFile = result
                prevFile = result

            # Successfully patched.
            assert pv is self and prevFile is self.tempFile
            return prevFile

        def applyPatch(self, origFile, patchFilename):
            """ Applies the named patch to the indicated original
            file, storing the results in a temporary file, and returns
            that temporary Filename.  Returns None on failure. """

            result = Filename.temporary('', 'patch_')
            p = Patchfile()
            if not p.apply(patchFilename, origFile, result):
                print("Internal patching failed: %s" % (patchFilename))
                return None

            return result

        def getNext(self, package):
            """ Gets the next patch in the chain towards this
            package. """
            for patch in self.toPatches:
                if patch.packageName == package.packageName and \
                   patch.platform == package.platform and \
                   patch.version == package.version and \
                   patch.hostUrl == package.hostUrl:
                    return patch.toPv

            return None

    class Patchfile:
        """ A single patchfile for a package. """

        def __init__(self, package):
            self.package = package
            self.packageName = package.packageName
            self.platform = package.platform
            self.version = package.version
            self.hostUrl = None

            # FileSpec for the patchfile itself
            self.file = None

            # FileSpec for the package file that the patch is applied to
            self.sourceFile = None

            # FileSpec for the package file that the patch generates
            self.targetFile = None

            # The PackageVersion corresponding to our sourceFile
            self.fromPv = None

            # The PackageVersion corresponding to our targetFile
            self.toPv = None

        def getSourceKey(self):
            """ Returns the key for locating the package that this
            patchfile can be applied to. """
            return (self.packageName, self.platform, self.version, self.hostUrl, self.sourceFile)

        def getTargetKey(self):
            """ Returns the key for locating the package that this
            patchfile will generate. """
            return (self.packageName, self.platform, self.version, self.hostUrl, self.targetFile)

        def fromFile(self, packageDir, patchFilename, sourceFile, targetFile):
            """ Creates the data structures from an existing patchfile
            on disk. """

            self.file = FileSpec()
            self.file.fromFile(packageDir, patchFilename)
            self.sourceFile = sourceFile
            self.targetFile = targetFile

        def loadXml(self, xpatch):
            """ Reads the data structures from an xml file. """

            self.packageName = xpatch.Attribute('name') or self.packageName
            self.platform = xpatch.Attribute('platform') or self.platform
            self.version = xpatch.Attribute('version') or self.version
            self.hostUrl = xpatch.Attribute('host') or self.hostUrl

            self.file = FileSpec()
            self.file.loadXml(xpatch)

            xsource = xpatch.FirstChildElement('source')
            if xsource:
                self.sourceFile = FileSpec()
                self.sourceFile.loadXml(xsource)

            xtarget = xpatch.FirstChildElement('target')
            if xtarget:
                self.targetFile = FileSpec()
                self.targetFile.loadXml(xtarget)

        def makeXml(self, package):
            xpatch = TiXmlElement('patch')

            if self.packageName != package.packageName:
                xpatch.SetAttribute('name', self.packageName)
            if self.platform != package.platform:
                xpatch.SetAttribute('platform', self.platform)
            if self.version != package.version:
                xpatch.SetAttribute('version', self.version)
            if self.hostUrl != package.hostUrl:
                xpatch.SetAttribute('host', self.hostUrl)

            self.file.storeXml(xpatch)

            xsource = TiXmlElement('source')
            self.sourceFile.storeMiniXml(xsource)
            xpatch.InsertEndChild(xsource)

            xtarget = TiXmlElement('target')
            self.targetFile.storeMiniXml(xtarget)
            xpatch.InsertEndChild(xtarget)

            return xpatch

    class Package:
        """ This is a particular package.  This contains all of the
        information needed to reconstruct the package's desc file. """

        def __init__(self, packageDesc, patchMaker, xpackage = None):
            self.packageDir = Filename(patchMaker.installDir, packageDesc.getDirname())
            self.packageDesc = packageDesc
            self.patchMaker = patchMaker
            self.contentsDocPackage = xpackage
            self.patchVersion = 1
            self.currentPv = None
            self.basePv = None
            self.topPv = None

            self.packageName = None
            self.platform = None
            self.version = None
            self.hostUrl = None
            self.currentFile = None
            self.baseFile = None

            self.doc = None
            self.anyChanges = False
            self.patches = []

        def getCurrentKey(self):
            """ Returns the key to locate the current version of this
            package. """

            return (self.packageName, self.platform, self.version, self.hostUrl, self.currentFile)

        def getBaseKey(self):
            """ Returns the key to locate the "base" or oldest version
            of this package. """

            return (self.packageName, self.platform, self.version, self.hostUrl, self.baseFile)

        def getTopKey(self):
            """ Returns the key to locate the "top" or newest version
            of this package. """

            return (self.packageName, self.platform, self.version, self.hostUrl, self.topFile)

        def getGenericKey(self, fileSpec):
            """ Returns the key that has the indicated hash. """
            return (self.packageName, self.platform, self.version, self.hostUrl, fileSpec)

        def readDescFile(self, doProcessing = False):
            """ Reads the existing package.xml file and stores it in
            this class for later rewriting.  if doProcessing is true,
            it may massage the file and the directory contents in
            preparation for building patches.  Returns true on
            success, false on failure. """

            self.anyChanges = False

            packageDescFullpath = Filename(self.patchMaker.installDir, self.packageDesc)
            self.doc = TiXmlDocument(packageDescFullpath.toOsSpecific())
            if not self.doc.LoadFile():
                print("Couldn't read %s" % (packageDescFullpath))
                return False

            xpackage = self.doc.FirstChildElement('package')
            if not xpackage:
                return False
            self.packageName = xpackage.Attribute('name')
            self.platform = xpackage.Attribute('platform')
            self.version = xpackage.Attribute('version')

            # All packages we defined in-line are assigned to the
            # "none" host.  TODO: support patching from packages on
            # other hosts, which means we'll need to fill in a value
            # here for those hosts.
            self.hostUrl = None

            self.currentFile = None
            self.baseFile = None
            self.topFile = None
            self.compressedFilename = None
            compressedFile = None

            # Assume there are changes for this version, until we
            # discover that there aren't.
            isNewVersion = True

            # Get the actual current version.
            xarchive = xpackage.FirstChildElement('uncompressed_archive')
            if xarchive:
                self.currentFile = FileSpec()
                self.currentFile.loadXml(xarchive)

            # Get the top_version--the top (newest) of the patch
            # chain.
            xarchive = xpackage.FirstChildElement('top_version')
            if xarchive:
                self.topFile = FileSpec()
                self.topFile.loadXml(xarchive)

                if self.topFile.hash == self.currentFile.hash:
                    # No new version this pass.
                    isNewVersion = False
                else:
                    # There's a new version this pass.  Update it.
                    self.anyChanges = True

            else:
                # If there isn't a top_version yet, we have to make
                # one, by duplicating the currentFile.
                self.topFile = copy.copy(self.currentFile)
                self.anyChanges = True

            # Get the current patch version.  If we have a
            # patch_version attribute, it refers to this particular
            # instance of the file, and that is the current patch
            # version number.  If we only have a last_patch_version
            # attribute, it means a patch has not yet been built for
            # this particular instance, and that number is the
            # previous version's patch version number.
            patchVersion = xpackage.Attribute('patch_version')
            if patchVersion:
                self.patchVersion = int(patchVersion)
            else:
                patchVersion = xpackage.Attribute('last_patch_version')
                if patchVersion:
                    self.patchVersion = int(patchVersion)
                    if isNewVersion:
                        self.patchVersion += 1
                self.anyChanges = True

            # Put the patchVersion in the compressed filename, for
            # cache-busting.  This means when the version changes, its
            # URL will also change, guaranteeing that users will
            # download the latest version, and not some stale cache
            # file.
            xcompressed = xpackage.FirstChildElement('compressed_archive')
            if xcompressed:
                compressedFile = FileSpec()
                compressedFile.loadXml(xcompressed)

                oldCompressedFilename = compressedFile.filename
                self.compressedFilename = oldCompressedFilename

                if doProcessing:
                    newCompressedFilename = '%s.%s.pz' % (self.currentFile.filename, self.patchVersion)
                    if newCompressedFilename != oldCompressedFilename:
                        oldCompressedPathname = Filename(self.packageDir, oldCompressedFilename)
                        newCompressedPathname = Filename(self.packageDir, newCompressedFilename)
                        if oldCompressedPathname.renameTo(newCompressedPathname):
                            compressedFile.fromFile(self.packageDir, newCompressedFilename)
                            compressedFile.storeXml(xcompressed)

                        self.compressedFilename = newCompressedFilename
                        self.anyChanges = True

            # Get the base_version--the bottom (oldest) of the patch
            # chain.
            xarchive = xpackage.FirstChildElement('base_version')
            if xarchive:
                self.baseFile = FileSpec()
                self.baseFile.loadXml(xarchive)
            else:
                # If there isn't a base_version yet, we have to make
                # one, by duplicating the currentFile.
                self.baseFile = copy.copy(self.currentFile)

                # Note that the we only store the compressed version
                # of base_filename on disk, but we store the md5 of
                # the uncompressed version in the xml file.  To
                # emphasize this, we name it without the .pz extension
                # in the xml file, even though the compressed file on
                # disk actually has a .pz extension.
                self.baseFile.filename += '.base'

                # Also duplicate the (compressed) file itself.
                if doProcessing and self.compressedFilename:
                    fromPathname = Filename(self.packageDir, self.compressedFilename)
                    toPathname = Filename(self.packageDir, self.baseFile.filename + '.pz')
                    fromPathname.copyTo(toPathname)
                self.anyChanges = True

            self.patches = []
            xpatch = xpackage.FirstChildElement('patch')
            while xpatch:
                patchfile = PatchMaker.Patchfile(self)
                patchfile.loadXml(xpatch)
                self.patches.append(patchfile)
                xpatch = xpatch.NextSiblingElement('patch')

            return True

        def writeDescFile(self):
            """ Rewrites the desc file with the new patch
            information. """

            if not self.anyChanges:
                # No need to rewrite.
                return

            xpackage = self.doc.FirstChildElement('package')
            if not xpackage:
                return

            packageSeq = SeqValue()
            packageSeq.loadXml(xpackage, 'seq')
            packageSeq += 1
            packageSeq.storeXml(xpackage, 'seq')

            # Remove all of the old patch entries from the desc file
            # we read earlier.
            xremove = []
            for value in ['base_version', 'top_version', 'patch']:
                xpatch = xpackage.FirstChildElement(value)
                while xpatch:
                    xremove.append(xpatch)
                    xpatch = xpatch.NextSiblingElement(value)

            for xelement in xremove:
                xpackage.RemoveChild(xelement)

            xpackage.RemoveAttribute('last_patch_version')

            # Now replace them with the current patch information.
            xpackage.SetAttribute('patch_version', str(self.patchVersion))

            xarchive = TiXmlElement('base_version')
            self.baseFile.storeXml(xarchive)
            xpackage.InsertEndChild(xarchive)

            # The current version is now the top version.
            xarchive = TiXmlElement('top_version')
            self.currentFile.storeXml(xarchive)
            xpackage.InsertEndChild(xarchive)

            for patchfile in self.patches:
                xpatch = patchfile.makeXml(self)
                xpackage.InsertEndChild(xpatch)

            self.doc.SaveFile()

            # Also copy the seq to the import desc file, for
            # documentation purposes.

            importDescFilename = str(self.packageDesc)[:-3] + 'import.xml'
            importDescFullpath = Filename(self.patchMaker.installDir, importDescFilename)
            doc = TiXmlDocument(importDescFullpath.toOsSpecific())
            if doc.LoadFile():
                xpackage = doc.FirstChildElement('package')
                if xpackage:
                    packageSeq.storeXml(xpackage, 'seq')
                    doc.SaveFile()
            else:
                print("Couldn't read %s" % (importDescFullpath))

            if self.contentsDocPackage:
                # Now that we've rewritten the xml file, we have to
                # change the contents.xml file that references it to
                # indicate the new file hash.
                fileSpec = FileSpec()
                fileSpec.fromFile(self.patchMaker.installDir, self.packageDesc)
                fileSpec.storeXml(self.contentsDocPackage)

                # Also important to update the import.xml hash.
                ximport = self.contentsDocPackage.FirstChildElement('import')
                if ximport:
                    fileSpec = FileSpec()
                    fileSpec.fromFile(self.patchMaker.installDir, importDescFilename)
                    fileSpec.storeXml(ximport)

                # Also copy the package seq value into the
                # contents.xml file, mainly for documentation purposes
                # (the authoritative seq value is within the desc
                # file).
                packageSeq.storeXml(self.contentsDocPackage, 'seq')


    # PatchMaker constructor.
    def __init__(self, installDir):
        self.installDir = installDir
        self.packageVersions = {}
        self.packages = []

    def buildPatches(self, packageNames = None):
        """ Makes the patches required in a particular directory
        structure on disk.  If packageNames is None, this makes
        patches for all packages; otherwise, it should be a list of
        package name strings, limiting the set of packages that are
        processed. """

        if not self.readContentsFile():
            return False
        self.buildPatchChains()
        if packageNames is None:
            self.processAllPackages()
        else:
            self.processSomePackages(packageNames)

        self.writeContentsFile()
        self.cleanup()
        return True

    def cleanup(self):
        """ Should be called on exit to remove temporary files and
        such created during processing. """

        for pv in self.packageVersions.values():
            pv.cleanup()

    def getPatchChainToCurrent(self, descFilename, fileSpec):
        """ Reads the package defined in the indicated desc file, and
        constructs a patch chain from the version represented by
        fileSpec to the current version of this package, if possible.
        Returns the patch chain if successful, or None otherwise. """

        package = self.readPackageDescFile(descFilename)
        if not package:
            return None

        self.buildPatchChains()
        fromPv = self.getPackageVersion(package.getGenericKey(fileSpec))
        toPv = package.currentPv

        patchChain = None
        if toPv and fromPv:
            patchChain = toPv.getPatchChain(fromPv)

        return patchChain

    def readPackageDescFile(self, descFilename):
        """ Reads a desc file associated with a particular package,
        and adds the package to self.packages.  Returns the Package
        object, or None on failure. """

        package = self.Package(Filename(descFilename), self)
        if not package.readDescFile(doProcessing = False):
            return None

        self.packages.append(package)
        return package

    def readContentsFile(self):
        """ Reads the contents.xml file at the beginning of
        processing. """

        contentsFilename = Filename(self.installDir, 'contents.xml')
        doc = TiXmlDocument(contentsFilename.toOsSpecific())
        if not doc.LoadFile():
            # Couldn't read file.
            print("couldn't read %s" % (contentsFilename))
            return False

        xcontents = doc.FirstChildElement('contents')
        if xcontents:
            contentsSeq = SeqValue()
            contentsSeq.loadXml(xcontents)
            contentsSeq += 1
            contentsSeq.storeXml(xcontents)

            xpackage = xcontents.FirstChildElement('package')
            while xpackage:
                solo = xpackage.Attribute('solo')
                solo = int(solo or '0')
                filename = xpackage.Attribute('filename')
                if filename and not solo:
                    filename = Filename(filename)
                    package = self.Package(filename, self, xpackage)
                    package.readDescFile(doProcessing = True)
                    self.packages.append(package)

                xpackage = xpackage.NextSiblingElement('package')

        self.contentsDoc = doc

        return True

    def writeContentsFile(self):
        """ Writes the contents.xml file at the end of processing. """

        # We also have to write the desc file for all packages that
        # might need it, because we might have changed some of them on
        # read.
        for package in self.packages:
            package.writeDescFile()

        # The above writeDescFile() call should also update each
        # package's element within the contents.xml document, so all
        # we have to do now is write out the document.
        self.contentsDoc.SaveFile()

    def getPackageVersion(self, key):
        """ Returns a shared PackageVersion object for the indicated
        key. """

        packageName, platform, version, hostUrl, file = key

        # We actually key on the hash, not the FileSpec itself.
        k = (packageName, platform, version, hostUrl, file.hash)
        pv = self.packageVersions.get(k, None)
        if not pv:
            pv = self.PackageVersion(*key)
            self.packageVersions[k] = pv
        return pv

    def buildPatchChains(self):
        """ Builds up the chains of PackageVersions and the patchfiles
        that connect them. """

        self.patchFilenames = {}

        for package in self.packages:
            if not package.baseFile:
                # This package doesn't have any versions yet.
                continue

            currentPv = self.getPackageVersion(package.getCurrentKey())
            package.currentPv = currentPv
            currentPv.packageCurrent = package
            currentPv.printName = package.currentFile.filename

            basePv = self.getPackageVersion(package.getBaseKey())
            package.basePv = basePv
            basePv.packageBase = package
            basePv.printName = package.baseFile.filename

            topPv = self.getPackageVersion(package.getTopKey())
            package.topPv = topPv
            topPv.packageTop = package

            for patchfile in package.patches:
                self.recordPatchfile(patchfile)

    def recordPatchfile(self, patchfile):
        """ Adds the indicated patchfile to the patch chains. """
        self.patchFilenames[patchfile.file.filename] = patchfile

        fromPv = self.getPackageVersion(patchfile.getSourceKey())
        patchfile.fromPv = fromPv
        fromPv.toPatches.append(patchfile)

        toPv = self.getPackageVersion(patchfile.getTargetKey())
        patchfile.toPv = toPv
        toPv.fromPatches.append(patchfile)
        toPv.printName = patchfile.file.filename

    def processSomePackages(self, packageNames):
        """ Builds missing patches only for the named packages. """

        remainingNames = packageNames[:]
        for package in self.packages:
            if package.packageName in packageNames:
                self.processPackage(package)
            if package.packageName in remainingNames:
                remainingNames.remove(package.packageName)

        if remainingNames:
            print("Unknown packages: %s" % (remainingNames,))

    def processAllPackages(self):
        """ Walks through the list of packages, and builds missing
        patches for each one. """

        for package in self.packages:
            self.processPackage(package)

    def processPackage(self, package):
        """ Builds missing patches for the indicated package. """

        if not package.baseFile:
            # No versions.
            return

        # What's the current version on the top of the tree?
        topPv = package.topPv
        currentPv = package.currentPv

        if topPv != currentPv:
            # They're different, so build a new patch.
            filename = Filename(package.currentFile.filename + '.%s.patch' % (package.patchVersion))
            assert filename not in self.patchFilenames
            if not self.buildPatch(topPv, currentPv, package, filename):
                raise Exception("Couldn't build patch.")

    def buildPatch(self, v1, v2, package, patchFilename):
        """ Builds a patch from PackageVersion v1 to PackageVersion
        v2, and stores it in patchFilename.pz.  Returns true on
        success, false on failure."""

        pathname = Filename(package.packageDir, patchFilename)
        if not self.buildPatchFile(v1.getFile(), v2.getFile(), pathname,
                                   v1.printName, v2.printName):
            return False

        compressedPathname = Filename(pathname + '.pz')
        compressedPathname.unlink()
        if not compressFile(pathname, compressedPathname, 9):
            raise Exception("Couldn't compress patch.")
        pathname.unlink()

        patchfile = self.Patchfile(package)
        patchfile.fromFile(package.packageDir, patchFilename + '.pz',
                           v1.file, v2.file)
        package.patches.append(patchfile)
        package.anyChanges = True

        self.recordPatchfile(patchfile)

        return True

    def buildPatchFile(self, origFilename, newFilename, patchFilename,
                       printOrigName, printNewName):
        """ Creates a patch file from origFilename to newFilename,
        storing the result in patchFilename.  Returns true on success,
        false on failure. """

        if not origFilename.exists():
            # No original version to patch from.
            return False

        print("Building patch from %s to %s" % (printOrigName, printNewName))
        patchFilename.unlink()
        p = Patchfile()  # The C++ class
        if p.build(origFilename, newFilename, patchFilename):
            return True

        # Unable to build a patch for some reason.
        patchFilename.unlink()
        return False
