// Filename: gtkStatsGraph.cxx
// Created by:  drose (16Jan06)
//
////////////////////////////////////////////////////////////////////
//
// PANDA 3D SOFTWARE
// Copyright (c) 2001 - 2004, Disney Enterprises, Inc.  All rights reserved
//
// All use of this software is subject to the terms of the Panda 3d
// Software license.  You should have received a copy of this license
// along with this source code; you will also find a current copy of
// the license at http://etc.cmu.edu/panda3d/docs/license/ .
//
// To contact the maintainers of this program write to
// panda3d-general@lists.sourceforge.net .
//
////////////////////////////////////////////////////////////////////

#include "gtkStatsGraph.h"
#include "gtkStatsMonitor.h"
#include "gtkStatsLabelStack.h"

const GdkColor GtkStatsGraph::rgb_white = {
  0, 0xffff, 0xffff, 0xffff
};
const GdkColor GtkStatsGraph::rgb_light_gray = {
  0, 0x9a9a, 0x9a9a, 0x9a9a,
};
const GdkColor GtkStatsGraph::rgb_dark_gray = {
  0, 0x3333, 0x3333, 0x3333,
};
const GdkColor GtkStatsGraph::rgb_black = {
  0, 0x0000, 0x0000, 0x0000
};
const GdkColor GtkStatsGraph::rgb_user_guide_bar = {
  0, 0x8282, 0x9696, 0xffff
};

////////////////////////////////////////////////////////////////////
//     Function: GtkStatsGraph::Constructor
//       Access: Public
//  Description:
////////////////////////////////////////////////////////////////////
GtkStatsGraph::
GtkStatsGraph(GtkStatsMonitor *monitor) :
  _monitor(monitor)
{
  _parent_window = NULL;
  _window = NULL;
  _graph_window = NULL;
  _scale_area = NULL;

  GtkWidget *parent_window = monitor->get_window();

  GdkDisplay *display = gdk_drawable_get_display(parent_window->window);
  _hand_cursor = gdk_cursor_new_for_display(display, GDK_HAND2);

  _pixmap = 0;
  _pixmap_gc = 0;

  _pixmap_xsize = 0;
  _pixmap_ysize = 0;

  _window = gtk_window_new(GTK_WINDOW_TOPLEVEL);

  gtk_window_set_transient_for(GTK_WINDOW(_window), GTK_WINDOW(parent_window));
  gtk_window_set_destroy_with_parent(GTK_WINDOW(_window), TRUE);
  gtk_widget_add_events(_window, 
			GDK_BUTTON_PRESS_MASK | GDK_BUTTON_RELEASE_MASK |
			GDK_POINTER_MOTION_MASK);
  g_signal_connect(G_OBJECT(_window), "delete_event",
		   G_CALLBACK(window_delete_event), this);
  g_signal_connect(G_OBJECT(_window), "destroy",
		   G_CALLBACK(window_destroy), this);
  g_signal_connect(G_OBJECT(_window), "button_press_event",  
		   G_CALLBACK(button_press_event_callback), this);
  g_signal_connect(G_OBJECT(_window), "button_release_event",  
		   G_CALLBACK(button_release_event_callback), this);
  g_signal_connect(G_OBJECT(_window), "motion_notify_event",  
		   G_CALLBACK(motion_notify_event_callback), this);

  _graph_window = gtk_drawing_area_new();
  gtk_widget_add_events(_graph_window, 
			GDK_BUTTON_PRESS_MASK | GDK_BUTTON_RELEASE_MASK |
			GDK_POINTER_MOTION_MASK);
  g_signal_connect(G_OBJECT(_graph_window), "expose_event",  
		   G_CALLBACK(graph_expose_callback), this);
  g_signal_connect(G_OBJECT(_graph_window), "configure_event",  
		   G_CALLBACK(configure_graph_callback), this);
  g_signal_connect(G_OBJECT(_graph_window), "button_press_event",  
		   G_CALLBACK(button_press_event_callback), this);
  g_signal_connect(G_OBJECT(_graph_window), "button_release_event",  
		   G_CALLBACK(button_release_event_callback), this);
  g_signal_connect(G_OBJECT(_graph_window), "motion_notify_event",  
		   G_CALLBACK(motion_notify_event_callback), this);

  // A Frame to hold the graph.
  GtkWidget *graph_frame = gtk_frame_new(NULL);
  gtk_frame_set_shadow_type(GTK_FRAME(graph_frame), GTK_SHADOW_IN);
  gtk_container_add(GTK_CONTAINER(graph_frame), _graph_window);

  // A VBox to hold the graph's frame, and any numbers (scale legend?
  // total?) above it.
  _graph_vbox = gtk_vbox_new(FALSE, 0);
  gtk_box_pack_end(GTK_BOX(_graph_vbox), graph_frame,
		   TRUE, TRUE, 0);

  // An HBox to hold the graph's frame, and the scale legend to the
  // right of it.
  _graph_hbox = gtk_hbox_new(FALSE, 0);
  gtk_box_pack_start(GTK_BOX(_graph_hbox), _graph_vbox,
		     TRUE, TRUE, 0);

  // An HPaned to hold the label stack and the graph hbox.
  _hpaned = gtk_hpaned_new();
  gtk_container_add(GTK_CONTAINER(_window), _hpaned);
  gtk_container_set_border_width(GTK_CONTAINER(_window), 8);

  gtk_paned_pack1(GTK_PANED(_hpaned), _label_stack.get_widget(), TRUE, TRUE);
  gtk_paned_pack2(GTK_PANED(_hpaned), _graph_hbox, TRUE, TRUE);

  _drag_mode = DM_none;
  _potential_drag_mode = DM_none;
  _drag_scale_start = 0.0f;

  _pause = false;
}

////////////////////////////////////////////////////////////////////
//     Function: GtkStatsGraph::Destructor
//       Access: Public, Virtual
//  Description:
////////////////////////////////////////////////////////////////////
GtkStatsGraph::
~GtkStatsGraph() {
  _monitor = (GtkStatsMonitor *)NULL;
  release_pixmap();
  
  Brushes::iterator bi;
  for (bi = _brushes.begin(); bi != _brushes.end(); ++bi) {
    GdkGC *gc = (*bi).second;
    g_object_unref(gc);
  }

  gtk_widget_destroy(_window);
}

////////////////////////////////////////////////////////////////////
//     Function: GtkStatsGraph::new_collector
//       Access: Public, Virtual
//  Description: Called whenever a new Collector definition is
//               received from the client.
////////////////////////////////////////////////////////////////////
void GtkStatsGraph::
new_collector(int new_collector) {
}

////////////////////////////////////////////////////////////////////
//     Function: GtkStatsGraph::new_data
//       Access: Public, Virtual
//  Description: Called whenever new data arrives.
////////////////////////////////////////////////////////////////////
void GtkStatsGraph::
new_data(int thread_index, int frame_number) {
}

////////////////////////////////////////////////////////////////////
//     Function: GtkStatsGraph::force_redraw
//       Access: Public, Virtual
//  Description: Called when it is necessary to redraw the entire graph.
////////////////////////////////////////////////////////////////////
void GtkStatsGraph::
force_redraw() {
}

////////////////////////////////////////////////////////////////////
//     Function: GtkStatsGraph::changed_graph_size
//       Access: Public, Virtual
//  Description: Called when the user has resized the window, forcing
//               a resize of the graph.
////////////////////////////////////////////////////////////////////
void GtkStatsGraph::
changed_graph_size(int graph_xsize, int graph_ysize) {
}

////////////////////////////////////////////////////////////////////
//     Function: GtkStatsGraph::set_time_units
//       Access: Public, Virtual
//  Description: Called when the user selects a new time units from
//               the monitor pulldown menu, this should adjust the
//               units for the graph to the indicated mask if it is a
//               time-based graph.
////////////////////////////////////////////////////////////////////
void GtkStatsGraph::
set_time_units(int unit_mask) {
}

////////////////////////////////////////////////////////////////////
//     Function: GtkStatsGraph::set_scroll_speed
//       Access: Public
//  Description: Called when the user selects a new scroll speed from
//               the monitor pulldown menu, this should adjust the
//               speed for the graph to the indicated value.
////////////////////////////////////////////////////////////////////
void GtkStatsGraph::
set_scroll_speed(float scroll_speed) {
}

////////////////////////////////////////////////////////////////////
//     Function: GtkStatsGraph::set_pause
//       Access: Public
//  Description: Changes the pause flag for the graph.  When this flag
//               is true, the graph does not update in response to new
//               data.
////////////////////////////////////////////////////////////////////
void GtkStatsGraph::
set_pause(bool pause) {
  _pause = pause;
}

////////////////////////////////////////////////////////////////////
//     Function: GtkStatsGraph::user_guide_bars_changed
//       Access: Public
//  Description: Called when the user guide bars have been changed.
////////////////////////////////////////////////////////////////////
void GtkStatsGraph::
user_guide_bars_changed() {
  if (_scale_area != NULL) {
    gtk_widget_queue_draw(_scale_area);
  }
  gtk_widget_queue_draw(_graph_window);
}

////////////////////////////////////////////////////////////////////
//     Function: GtkStatsGraph::clicked_label
//       Access: Public, Virtual
//  Description: Called when the user single-clicks on a label.
////////////////////////////////////////////////////////////////////
void GtkStatsGraph::
clicked_label(int collector_index) {
}

////////////////////////////////////////////////////////////////////
//     Function: GtkStatsGraph::close
//       Access: Protected
//  Description: Should be called when the user closes the associated
//               window.  This tells the monitor to remove the graph.
////////////////////////////////////////////////////////////////////
void GtkStatsGraph::
close() {
  GtkStatsMonitor *monitor = _monitor;
  _monitor = (GtkStatsMonitor *)NULL;
  if (monitor != (GtkStatsMonitor *)NULL) {
    monitor->remove_graph(this);
  }
}

////////////////////////////////////////////////////////////////////
//     Function: GtkStatsGraph::get_collector_gc
//       Access: Protected
//  Description: Returns a GC suitable for drawing in the indicated
//               collector's color.
////////////////////////////////////////////////////////////////////
GdkGC *GtkStatsGraph::
get_collector_gc(int collector_index) {
  Brushes::iterator bi;
  bi = _brushes.find(collector_index);
  if (bi != _brushes.end()) {
    return (*bi).second;
  }

  // Ask the monitor what color this guy should be.
  RGBColorf rgb = _monitor->get_collector_color(collector_index);

  GdkColor c;
  c.red = (int)(rgb[0] * 65535.0f);
  c.green = (int)(rgb[1] * 65535.0f);
  c.blue = (int)(rgb[2] * 65535.0f);
  GdkGC *gc = gdk_gc_new(_pixmap);
  //  g_object_ref(gc);  // Should this be ref_sink?
  gdk_gc_set_rgb_fg_color(gc, &c);

  _brushes[collector_index] = gc;
  return gc;
}

////////////////////////////////////////////////////////////////////
//     Function: GtkStatsGraph::additional_graph_window_paint
//       Access: Protected, Virtual
//  Description: This is called during the servicing of expose_event;
//               it gives a derived class opportunity to do some
//               further painting into the graph window.
////////////////////////////////////////////////////////////////////
void GtkStatsGraph::
additional_graph_window_paint() {
}

////////////////////////////////////////////////////////////////////
//     Function: GtkStatsGraph::consider_drag_start
//       Access: Protected, Virtual
//  Description: Based on the mouse position within the graph window,
//               look for draggable things the mouse might be hovering
//               over and return the appropriate DragMode enum or
//               DM_none if nothing is indicated.
////////////////////////////////////////////////////////////////////
GtkStatsGraph::DragMode GtkStatsGraph::
consider_drag_start(int graph_x, int graph_y) {
  return DM_none;
}

////////////////////////////////////////////////////////////////////
//     Function: GtkStatsGraph::set_drag_mode
//       Access: Protected, Virtual
//  Description: This should be called whenever the drag mode needs to
//               change state.  It provides hooks for a derived class
//               to do something special.
////////////////////////////////////////////////////////////////////
void GtkStatsGraph::
set_drag_mode(GtkStatsGraph::DragMode drag_mode) {
  _drag_mode = drag_mode;
}

////////////////////////////////////////////////////////////////////
//     Function: GtkStatsGraph::handle_button_press
//       Access: Protected, Virtual
//  Description: Called when the mouse button is depressed within the
//               window, or any nested window.
////////////////////////////////////////////////////////////////////
gboolean GtkStatsGraph::
handle_button_press(GtkWidget *widget, int graph_x, int graph_y,
		    bool double_click) {
  if (_potential_drag_mode != DM_none) {
    set_drag_mode(_potential_drag_mode);
    _drag_start_x = graph_x;
    _drag_start_y = graph_y;
    //    SetCapture(_window);
  }
  return TRUE;
}

////////////////////////////////////////////////////////////////////
//     Function: GtkStatsGraph::handle_button_release
//       Access: Protected, Virtual
//  Description: Called when the mouse button is released within the
//               window, or any nested window.
////////////////////////////////////////////////////////////////////
gboolean GtkStatsGraph::
handle_button_release(GtkWidget *widget, int graph_x, int graph_y) {
  set_drag_mode(DM_none);
  //  ReleaseCapture();

  return handle_motion(widget, graph_x, graph_y);
}

////////////////////////////////////////////////////////////////////
//     Function: GtkStatsGraph::handle_motion
//       Access: Protected, Virtual, Static
//  Description: Called when the mouse is moved within the
//               window, or any nested window.
////////////////////////////////////////////////////////////////////
gboolean GtkStatsGraph::
handle_motion(GtkWidget *widget, int graph_x, int graph_y) {
  _potential_drag_mode = consider_drag_start(graph_x, graph_y);

  if (_potential_drag_mode == DM_guide_bar ||
      _drag_mode == DM_guide_bar) {
    gdk_window_set_cursor(_window->window, _hand_cursor);

  } else {
    gdk_window_set_cursor(_window->window, NULL);
  }

  return TRUE;
}

////////////////////////////////////////////////////////////////////
//     Function: GtkStatsGraph::setup_pixmap
//       Access: Private
//  Description: Sets up a backing-store bitmap of the indicated size.
////////////////////////////////////////////////////////////////////
void GtkStatsGraph::
setup_pixmap(int xsize, int ysize) {
  release_pixmap();

  _pixmap_xsize = max(xsize, 0);
  _pixmap_ysize = max(ysize, 0);

  _pixmap = gdk_pixmap_new(_graph_window->window, _pixmap_xsize, _pixmap_ysize, -1);
  //  g_object_ref(_pixmap);  // Should this be ref_sink?
  _pixmap_gc = gdk_gc_new(_pixmap);
  //  g_object_ref(_pixmap_gc);   // Should this be ref_sink?

  gdk_gc_set_rgb_fg_color(_pixmap_gc, &rgb_white);
  gdk_draw_rectangle(_pixmap, _pixmap_gc, TRUE, 0, 0, 
		     _pixmap_xsize, _pixmap_ysize);
}

////////////////////////////////////////////////////////////////////
//     Function: GtkStatsGraph::release_pixmap
//       Access: Private
//  Description: Frees the backing-store bitmap created by
//               setup_pixmap().
////////////////////////////////////////////////////////////////////
void GtkStatsGraph::
release_pixmap() {
  if (_pixmap != NULL) {
    g_object_unref(_pixmap);
    g_object_unref(_pixmap_gc);
  }
}

////////////////////////////////////////////////////////////////////
//     Function: GtkStatsGraph::window_delete_event
//       Access: Private, Static
//  Description: Callback when the window is closed by the user.
////////////////////////////////////////////////////////////////////
gboolean GtkStatsGraph::
window_delete_event(GtkWidget *widget, GdkEvent *event, gpointer data) {
  // Returning FALSE to indicate we should destroy the window
  // when the user selects "close".
  return FALSE;
}

////////////////////////////////////////////////////////////////////
//     Function: GtkStatsGraph::window_destroy
//       Access: Private, Static
//  Description: Callback when the window is destroyed by the system
//               (or by delete_event).
////////////////////////////////////////////////////////////////////
void GtkStatsGraph::
window_destroy(GtkWidget *widget, gpointer data) {
  GtkStatsGraph *self = (GtkStatsGraph *)data;
  self->close();
}

////////////////////////////////////////////////////////////////////
//     Function: GtkStatsGraph::graph_expose_callback
//       Access: Private, Static
//  Description: Fills in the graph window.
////////////////////////////////////////////////////////////////////
gboolean GtkStatsGraph::
graph_expose_callback(GtkWidget *widget, GdkEventExpose *event, gpointer data) {
  GtkStatsGraph *self = (GtkStatsGraph *)data;

  if (self->_pixmap != NULL) {
    gdk_draw_drawable(self->_graph_window->window, 
		      self->_graph_window->style->fg_gc[0],
		      self->_pixmap, 0, 0, 0, 0,
		      self->_pixmap_xsize, self->_pixmap_ysize);
  }

  self->additional_graph_window_paint();
    
  return TRUE;
}

////////////////////////////////////////////////////////////////////
//     Function: GtkStatsGraph::configure_graph_callback
//       Access: Private, Static
//  Description: Changes the size of the graph window
////////////////////////////////////////////////////////////////////
gboolean GtkStatsGraph::
configure_graph_callback(GtkWidget *widget, GdkEventConfigure *event, 
			 gpointer data) {
  GtkStatsGraph *self = (GtkStatsGraph *)data;

  self->changed_graph_size(event->width, event->height);
  self->setup_pixmap(event->width, event->height);
  self->force_redraw();
    
  return TRUE;
}

////////////////////////////////////////////////////////////////////
//     Function: GtkStatsGraph::button_press_event_callback
//       Access: Private, Static
//  Description: Called when the mouse button is depressed within the
//               graph window or main window.
////////////////////////////////////////////////////////////////////
gboolean GtkStatsGraph::
button_press_event_callback(GtkWidget *widget, GdkEventButton *event, 
			    gpointer data) {
  GtkStatsGraph *self = (GtkStatsGraph *)data;
  int graph_x, graph_y;
  gtk_widget_translate_coordinates(widget, self->_graph_window,
				   (int)event->x, (int)event->y,
				   &graph_x, &graph_y);

  bool double_click = (event->type == GDK_2BUTTON_PRESS);

  return self->handle_button_press(widget, graph_x, graph_y, double_click);
}

////////////////////////////////////////////////////////////////////
//     Function: GtkStatsGraph::button_release_event_callback
//       Access: Private, Static
//  Description: Called when the mouse button is released within the
//               graph window or main window.
////////////////////////////////////////////////////////////////////
gboolean GtkStatsGraph::
button_release_event_callback(GtkWidget *widget, GdkEventButton *event, 
			      gpointer data) {
  GtkStatsGraph *self = (GtkStatsGraph *)data;
  int graph_x, graph_y;
  gtk_widget_translate_coordinates(widget, self->_graph_window,
				   (int)event->x, (int)event->y,
				   &graph_x, &graph_y);

  return self->handle_button_release(widget, graph_x, graph_y);
}

////////////////////////////////////////////////////////////////////
//     Function: GtkStatsGraph::motion_notify_event_callback
//       Access: Private, Static
//  Description: Called when the mouse is moved within the
//               graph window or main window.
////////////////////////////////////////////////////////////////////
gboolean GtkStatsGraph::
motion_notify_event_callback(GtkWidget *widget, GdkEventMotion *event, 
			     gpointer data) {
  GtkStatsGraph *self = (GtkStatsGraph *)data;
  int graph_x, graph_y;
  gtk_widget_translate_coordinates(widget, self->_graph_window,
				   (int)event->x, (int)event->y,
				   &graph_x, &graph_y);

  return self->handle_motion(widget, graph_x, graph_y);
}
