#
# gtkui.py
#
# Copyright (C) 2016 Alan Wu <xrsquared@gmail.com>
#
# Basic plugin template created by:
# Copyright (C) 2008 Martijn Voncken <mvoncken@gmail.com>
# Copyright (C) 2007-2009 Andrew Resch <andrewresch@gmail.com>
# Copyright (C) 2009 Damien Churchill <damoxc@gmail.com>
# Copyright (C) 2010 Pedro Algarvio <pedro@algarvio.me>
#
# Deluge is free software.
#
# You may redistribute it and/or modify it under the terms of the
# GNU General Public License, as published by the Free Software
# Foundation; either version 3 of the License, or (at your option)
# any later version.
#
# deluge is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
# See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with deluge.    If not, write to:
# 	The Free Software Foundation, Inc.,
# 	51 Franklin Street, Fifth Floor
# 	Boston, MA  02110-1301, USA.
#
#    In addition, as a special exception, the copyright holders give
#    permission to link the code of portions of this program with the OpenSSL
#    library.
#    You must obey the GNU General Public License in all respects for all of
#    the code used other than OpenSSL. If you modify file(s) with this
#    exception, you may extend this exception to your version of the file(s),
#    but you are not obligated to do so. If you do not wish to do so, delete
#    this exception statement from your version. If you delete this exception
#    statement from all source files in the program, then also delete it here.
#

import gtk
import logging
import dbus
import dbus.service

from deluge.ui.client import client
from deluge.plugins.pluginbase import GtkPluginBase
import deluge.component as component
import deluge.common
import pkg_resources
import os.path

from common import get_resource

log = logging.getLogger(__name__)

class GtkUI(GtkPluginBase):
    def enable(self):
        self.glade = gtk.glade.XML(get_resource("config.glade"))

        component.get("Preferences").add_page("Better Open Folder", self.glade.get_widget("config_frame"))
        component.get("PluginManager").register_hook("on_apply_prefs", self.on_apply_prefs)
        component.get("PluginManager").register_hook("on_show_prefs", self.on_show_prefs)

        self.thunar_radio = self.glade.get_widget("thunar")
        self.freedesktop_radio = self.glade.get_widget("freedesktop")

        self.menubar = component.get("MenuBar")
        self.open_folder_widget = self.menubar.torrentmenu_glade.get_widget(
            "menuitem_open_folder")
        self.open_folder_widget.handler_block_by_func(
            self.menubar.on_menuitem_open_folder_activate)
        self.open_folder_handler_id = self.open_folder_widget.connect(
            "activate", self.open_folder)

        self.pending_open = []  # opens before config is obtained
        client.thunaropen.get_config().addCallback(self.cb_first_pref_get)

        self.get_dbus()

    def get_dbus(self):
        self.xfce_file_manager = None
        self.file_manager = None

        self.thunar_radio.set_sensitive(True)
        self.freedesktop_radio.set_sensitive(True)

        try:
            bus = dbus.SessionBus()
            xfce_file_manager_object = bus.get_object('org.xfce.FileManager', '/org/xfce/FileManager')
            self.xfce_file_manager = dbus.Interface(xfce_file_manager_object, 'org.xfce.FileManager')

            file_manager_object = bus.get_object('org.freedesktop.FileManager1', '/org/freedesktop/FileManager1')
            self.file_manager = dbus.Interface(file_manager_object, 'org.freedesktop.FileManager1')
        except Exception:
            log.debug("Something went wrong trying to get dbus interfaces")

        if not self.file_manager:
            self.freedesktop_radio.set_sensitive(False)
        if not self.xfce_file_manager:
            self.thunar_radio.set_sensitive(False)

    def cb_first_pref_get(self, config):
        self.open_method = config["open_method"]
        for e in self.pending_open:
            self.dispatch_open(*e)
        self.pending_open = None

    def dispatch_open(self, folder, file):
        if self.open_method == "thunar" and self.xfce_file_manager:
            self.thunar_open(folder, file)
        elif self.open_method == "freedesktop" and self.file_manager:
            self.freedesktop_open(folder, file)
        else:
            if self.open_method != "deluge":
                log.debug("Selected open method broke, falling back to deluge")
            self.deluge_open(folder, file)

    def open_folder(self, data=None):
        def _on_torrent_status(status):
            open_direction = how_to_open(status["save_path"], status["files"])
            if self.pending_open is not None:
                self.pending_open.append(open_direction)
            self.dispatch_open(*open_direction)

        for torrent_id in component.get("TorrentView").get_selected_torrents():
            component.get("SessionProxy").get_torrent_status(torrent_id, ["save_path", "files"]).addCallback(_on_torrent_status)

    def thunar_open(self, folder, file):
        if not file:
            return self.xfce_file_manager.DisplayFolder(folder, "", "")
        self.xfce_file_manager.DisplayFolderAndSelect(folder, file, "", "")

    def deluge_open(self, folder, _):
        timestamp = gtk.get_current_event_time()
        deluge.common.open_file(folder, timestamp=timestamp)

    def freedesktop_open(self, folder, file):
        if not file:
            return self.file_manager.ShowFolders([folder], "")
        return self.file_manager.ShowItems([os.path.join(folder, file)], '')

    def disable(self):
        self.open_folder_widget.handler_unblock_by_func(
            self.menubar.on_menuitem_open_folder_activate)

        self.open_folder_widget.disconnect_handler(self.open_folder_handler_id)

        component.get("Preferences").remove_page("ThunarOpen")
        component.get("PluginManager").deregister_hook("on_apply_prefs", self.on_apply_prefs)
        component.get("PluginManager").deregister_hook("on_show_prefs", self.on_show_prefs)

    def on_apply_prefs(self):
        log.debug("applying prefs for ThunarOpen")

        config = None
        for btn in self.glade.get_widget("thunar").get_group():
            if btn.get_active():
                name = btn.get_name()
                config = {
                    "open_method": name
                }
                self.open_method = name
                break
        client.thunaropen.set_config(config)

    def on_show_prefs(self):
        self.get_dbus()
        client.thunaropen.get_config().addCallback(self.cb_pref_get_config)

    def cb_pref_get_config(self, config):
        "callback for on show_prefs"
        self.glade.get_widget(config["open_method"]).set_active(True)

def how_to_open(save_path, files):
    first_path = files[0]["path"]
    if len(files) == 1:
        return (save_path, first_path)
    return os.path.join(save_path, os.path.dirname(first_path)), None