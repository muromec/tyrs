# -*- coding: utf-8 -*-
# Copyright © 2011 Nicolas Paris <nicolas.caen@gmail.com>
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import re
import os
import sys
#import time
import tyrs
import urwid
import curses
#import logging
from update import UpdateThread
from user import User
from utils import html_unescape, encode, get_source, get_urls
from widget import StatusWidget, HeaderWidget
from editor import TweetEditor
from keys import Keys


class Interface(object):

    def __init__(self):
        self.api        = tyrs.container['api']
        self.conf       = tyrs.container['conf']
        self.timelines  = tyrs.container['timelines']
        self.buffers    = tyrs.container['buffers']
        tyrs.container.add('interface', self)
        self.update_last_read_home()
        self.api.set_interface()
        self.regex_retweet     = re.compile('^RT @\w+:')
        self.refresh_token    = False
        self.stoped = False
        self.buffer           = 'home'
        self.charset = sys.stdout.encoding
        self.first_update()
        self.main_loop()

    def main_loop (self):

        palette = [
            ('body','dark blue', '', 'standout'),
            ('focus','dark red', '', 'standout'),
            ('head','light red', ''),
            ('info_msg', 'dark green', ''),
            ('warn_msg', 'dark red', ''),
            ('current_tab', 'light blue', ''),
            ('other_tab', 'dark blue', ''),
            ('read', 'dark blue', ''),
            ('unread', 'dark red', ''),
            ('hashtag', 'dark green', ''),
            ('attag', 'brown', ''),
            ('highlight', 'dark red', ''),
            ]


        items = []
        timeline = self.select_current_timeline()
        for i, status in enumerate(timeline.statuses):
            items.append(StatusWidget(i, status))

        self.header = HeaderWidget()
        self.listbox = urwid.ListBox(urwid.SimpleListWalker(items))
        self.main_frame = urwid.Frame(urwid.AttrWrap(self.listbox, 'body'), header=self.header)
        key_handle = Keys()
        self.loop = urwid.MainLoop(self.main_frame, palette, unhandled_input=key_handle.keystroke)
        update = UpdateThread()
        update.start()
        self.loop.run()
        update.stop()


    def reply(self):
        self.status = self.current_status()
        if hasattr(self.status, 'user'):
            nick = self.status.user.screen_name
        #FIXME: 
        #else:
            #self.direct_message()
        data = '@' + nick
        self.edit_status('reply', data)

    def reply_done(self, content):
        self.clean_edit()
        urwid.disconnect_signal(self, self.foot, 'done', self.reply_done)
        if content:
            self.api.post_tweet(content, self.status.id)

    def edit_status(self, action, content=''):
        self.foot = TweetEditor(content)
        self.main_frame.set_footer(self.foot)
        self.main_frame.set_focus('footer')
        if action == 'tweet':
            urwid.connect_signal(self.foot, 'done', self.tweet_done)
        elif action == 'reply':
            urwid.connect_signal(self.foot, 'done', self.reply_done)
        elif action == 'follow':
            urwid.connect_signal(self.foot, 'done', self.follow_done)
        elif action == 'unfollow':
            urwid.connect_signal(self.foot, 'done', self.unfollow_done)
        elif action == 'search':
            urwid.connect_signal(self.foot, 'done', self.search_done)
        elif action == 'public':
            urwid.connect_signal(self.foot, 'done', self.public_done)

    def tweet_done(self, content):
        self.clean_edit()
        urwid.disconnect_signal(self, self.foot, 'done', self.tweet_done)
        if content:
            self.api.post_tweet(encode(content))

    def follow_done(self, content):
        self.clean_edit()
        urwid.disconnect_signal(self, self.foot, 'done', self.follow_done)
        if content:
            self.api.create_friendship(content)

    def unfollow_done(self, content):
        self.clean_edit()
        urwid.disconnect_signal(self, self.foot, 'done', self.unfollow_done)
        if content:
            self.api.destroy_friendship(content)

    def search_done(self, content):
        self.clean_edit()
        urwid.disconnect_signal(self, self.foot, 'done', self.search_done)
        if content:
            self.api.search(content)

    def public_done(self, content):
        self.clean_edit()
        urwid.disconnect_signal(self, self.foot, 'done', self.public_done)
        if content:
            self.api.find_public_timeline(content)

    def clean_edit(self):
        self.main_frame.set_focus('body')
        self.main_frame.set_footer(None)




    def first_update(self):
        updates = ['home', 'direct', 'mentions', 'user_retweet', 'favorite']
        for buff in updates:
            self.api.update_timeline(buff)
            self.timelines[buff].reset()
            self.timelines[buff].all_read()

    def display_timeline (self):
        items = []
        timeline = self.select_current_timeline()
        for i, status in enumerate(timeline.statuses):
            items.append(StatusWidget(i, status))
        self.listbox = urwid.ListBox(urwid.SimpleListWalker(items))

        self.main_frame.set_body(urwid.AttrWrap(self.listbox, 'body'))
        self.display_flash_message()

    def redraw_screen (self):
        self.loop.draw_screen()

    def display_flash_message(self):
        try:
            header = HeaderWidget()
            self.main_frame.set_header(header)
            self.redraw_screen()
            self.api.flash_message.reset()
        except AttributeError:
            pass

    def erase_flash_message(self):
        self.api.flash_message.reset()
        self.display_flash_message()

    def change_buffer(self, buffer):
        self.buffer = buffer
        self.timelines[buffer].reset()
    
    def navigate_buffer(self, nav):
        '''Navigate with the arrow, mean nav should be -1 or +1'''
        index = self.buffers.index(self.buffer)
        new_index = index + nav
        if new_index >= 0 and new_index < len(self.buffers):
            self.change_buffer(self.buffers[new_index])

    def check_for_last_read(self, id):
        if self.buffer == 'home':
            if self.last_read_home == str(id):
                self.screen.hline(self.current_y, 1, '-', self.maxyx[1]-3)
                self.current_y += 1


    def select_current_timeline(self):
        return self.timelines[self.buffer]


    def display_help_bar(self):
        '''The help bar display at the bottom of the screen,
           for keysbinding reminder'''
        if self.conf.params['help']:
            maxyx = self.screen.getmaxyx()
            self.screen.addnstr(maxyx[0] -1, 2,
                'help:? up:%s down:%s tweet:%s retweet:%s reply:%s home:%s mentions:%s update:%s' %
                               (chr(self.conf.keys['up']),
                                chr(self.conf.keys['down']),
                                chr(self.conf.keys['tweet']),
                                chr(self.conf.keys['retweet']),
                                chr(self.conf.keys['reply']),
                                chr(self.conf.keys['home']),
                                chr(self.conf.keys['mentions']),
                                chr(self.conf.keys['update']),
                               ), maxyx[1] -4, self.get_color('text')
            )

    def clear_statuses(self):
        timeline = self.select_current_timeline()
        timeline.statuses = [timeline.statuses[0]]
        timeline.count_statuses()
        timeline.reset()

    def current_status(self):
        focus = self.listbox.get_focus()[0]
        return focus.status

    def move_down(self):
        timeline = self.select_current_timeline()
        if timeline.current < timeline.count - 1:
            if timeline.current >= timeline.last:
                timeline.first += 1
            timeline.current += 1
        else:
            self.lazzy_load()

    def lazzy_load(self):
        timeline = self.select_current_timeline()
        timeline.page += 1
        statuses = self.api.retreive_statuses(self.buffer, timeline.page)
        timeline.append_old_statuses(statuses)
        timeline.first += 1
        timeline.current += 1

    def move_up(self):
        timeline = self.select_current_timeline()
        if timeline.current > 0:
            # if we need to move up the list to display
            if timeline.current == timeline.first:
                timeline.first -= 1
            timeline.current -= 1

    def back_on_bottom(self):
        timeline = self.select_current_timeline()
        timeline.current = timeline.last

    def back_on_top(self):
        timeline = self.select_current_timeline()
        timeline.current = 0
        timeline.reset()

    def openurl(self):
        urls = get_urls(self.current_status().text)
        for url in urls:
            try:
                os.system(self.conf.params['openurl_command'] % url + '> /dev/null 2>&1')
            except:
                pass 

    def update_last_read_home(self):
        self.last_read_home = self.conf.load_last_read()

    def current_user_info(self):
        User(self.current_status().user)
