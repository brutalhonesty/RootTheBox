# -*- coding: utf-8 -*-
'''
Created on Mar 13, 2012

@author: moloch

    Copyright 2012 Root the Box

    Licensed under the Apache License, Version 2.0 (the "License");
    you may not use this file except in compliance with the License.
    You may obtain a copy of the License at

        http://www.apache.org/licenses/LICENSE-2.0

    Unless required by applicable law or agreed to in writing, software
    distributed under the License is distributed on an "AS IS" BASIS,
    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
    See the License for the specific language governing permissions and
    limitations under the License.
----------------------------------------------------------------------------

This file contains code for managing user accounts

'''


import os
import imghdr
import logging

from uuid import uuid4
from models import dbsession, User, Theme
from libs.Form import Form
from libs.SecurityDecorators import authenticated
from BaseHandlers import BaseHandler
from recaptcha.client import captcha


class HomeHandler(BaseHandler):

    @authenticated
    def get(self, *args, **kwargs):
        ''' Display the default user page '''
        user = self.get_current_user()
        if user.handle is 'God' or 'admin':
            self.render('admin/home.html', user=user)
        self.render('user/home.html', user=user)


class SettingsHandler(BaseHandler):
    ''' Modify user controlled attributes '''

    @authenticated
    def get(self, *args, **kwargs):
        ''' Display the user settings '''
        self.render_page()

    @authenticated
    def post(self, *args, **kwargs):
        ''' Calls function based on parameter '''
        post_functions = {
            '/avatar': self.post_avatar,
            '/password': self.post_password,
            '/theme': self.post_theme,
        }
        if len(args) == 1 and args[0] in post_functions:
            post_functions[args[0]]()
        else:
            self.render_page()

    def render_page(self, errors=None, success=None):
        ''' Small wrap for self.render to cut down on lenghty params '''
        current_theme = Theme.by_cssfile(self.session["theme"])
        self.render("user/settings.html",
            errors=errors,
            success=success,
            current_theme=current_theme
        )

    def post_avatar(self, *args, **kwargs):
        '''
        Saves avatar - Reads file header an only allows approved formats
        '''
        user = User.by_id(self.session['user_id'])
        if 'avatar' in self.request.files:
            if len(self.request.files['avatar'][0]['body']) < (1024 * 1024):
                if user.avatar == "default_avatar.jpeg":
                    user.avatar = unicode(uuid4()) + u".jpeg"
                ext = imghdr.what(
                    "", h=self.request.files['avatar'][0]['body']
                )
                avatar_path = str(self.application.settings['avatar_dir'] +
                    '/' + user.avatar)
                if ext in ['png', 'jpeg', 'gif', 'bmp']:
                    if os.path.exists(avatar_path):
                        os.unlink(avatar_path)
                    user.avatar = unicode(user.avatar[:user.avatar.rfind('.')]
                        + "." + ext)
                    file_path = str(self.application.settings['avatar_dir'] +
                        '/' + user.avatar)
                    avatar = open(file_path, 'wb')
                    avatar.write(self.request.files['avatar'][0]['body'])
                    avatar.close()
                    dbsession.add(user)
                    dbsession.flush()
                    self.render_page(success=["Successfully changed avatar"])
                else:
                    self.render_page(
                        errors=[str("Invalid image format, avatar must be:"
                            + ".png .jpeg .gif or .bmp")]
                    )
            else:
                self.render_page(errors=["The image is too large"])
        else:
            self.render_page(errors=["Please provide and image"])

    def post_password(self, *args, **kwargs):
        ''' Called on POST request for password change '''
        form = Form(
            old_password="Please enter your old password",
            new_password="Please enter a new password",
            new_password_two="Please confirm your new password",
            recaptcha_challenge_field="Please solve the captcha",
            recaptcha_response_field="Please solve the captcha",
        )
        if form.validate(self.request.arguments):
            if self.check_recaptcha():
                self.set_password(
                    self.get_current_user(),
                    self.get_argument('old_password'),
                    self.get_argument('new_password'),
                    self.get_argument('new_password_two')
                )
            else:
                self.render_page(errors=["Invalid recaptcha"])
        else:
            self.render_page(errors=form.errors)

    def post_theme(self, *args, **kwargs):
        ''' Change per-user theme '''
        form = Form(theme_uuid="Please select a theme",)
        if form.validate(self.request.arguments):
            theme = Theme.by_uuid(self.get_argument('theme_uuid'))
            if theme is not None:
                self.session['theme'] = ''.join(theme.cssfile)
                self.session.save()
                user = self.get_current_user()
                user.theme_id = theme.id
                dbsession.add(user)
                dbsession.flush()
                self.render_page()
            else:
                self.render_page(errors=["Theme does not exist."])
        else:
            self.render_page(errors=form.errors)

    def set_password(self, user, old_password, new_password, new_password2):
        ''' Sets a users password '''
        if user.validate_password(old_password):
            if new_password == new_password2:
                if len(new_password) <= self.config.max_password_length:
                    user.password = new_password
                    dbsession.add(user)
                    dbsession.flush()
                    self.render_page(success=["Successfully updated password"])
                else:
                    message = "Password must be less than %d chars" % (
                        self.config.max_password_length,
                    )
                    self.render_page(errors=[message])
            else:
                self.render_page(errors=["New password's didn't match"])
        else:
            self.render_page(errors=["Invalid old password"])

    def check_recaptcha(self):
        ''' Checks recaptcha '''
        if self.config.recaptcha_enable:
            response = None
            try:
                response = captcha.submit(
                    self.get_argument('recaptcha_challenge_field'),
                    self.get_argument('recaptcha_response_field'),
                    self.config.recaptcha_private_key,
                    self.request.remote_ip
                )
            except KeyError:
                logging.exception("Recaptcha API called failed.")
            if response is not None and response.is_valid:
                return True
            else:
                user = self.get_current_user()
                logging.warning("%s failed a captcha test." % user.handle)
                return False
        else:
            return True
