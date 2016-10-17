#!/usr/bin/env python3
from queue import Queue
from sys import stderr
from threading import Thread

import requests
from lxml import etree

from Sympal.MailingList import MailingList


class Sympa:
    # XPath for the 'list of lists' on sympa home page
    LISTS_XPATH = etree.XPath('//*[@id="Menus"]/div[3]/ul/li/a/@href')
    MAX_CONCURRENT_REQUEST_THREADS = 4

    def __enter__(self):
        return (self)

    def __init__(self, url):
        self.url = url
        self.session = requests.session()
        self.lists = {}

    def __exit__(self, ex_type, ex_val, traceback):
        self.log_out()
        self.close()

    def __logged_in(self, page):
        # Check a page for the ability to log out -- signifying logged in
        return ('action_logout' in page.text)

    def __populate_all_lists(self):
        # Populate all lists using concurrent requests
        concurrent = self.MAX_CONCURRENT_REQUEST_THREADS
        q = Queue(concurrent * 2)

        def populate():
            while True:
                name = q.get()
                self.lists[name].update()  # Update the MailingList
                q.task_done()

        for i in range(concurrent):
            t = Thread(target=populate)
            t.daemon = True
            t.start()

        for name, l in self.lists.items():
            q.put(name)

        q.join()

    def __populate_all(self, page):
        # Get list names, then populate all lists
        self.__get_list_names(page)
        self.__populate_all_lists()

    def __get_list_names(self, page):
        # Get the names of lists from the sidebar 'list of lists'
        root = self.get_page_root(page)
        links = self.LISTS_XPATH(root)
        names = (link.rsplit('/', 1)[1] for link in links)
        self.lists = {}

        for name in names:
            self.lists[name] = MailingList(self, name)

    def get_page(self, *args):
        """
        Get a page using the current session and sympa url, where args
        signify parts of a uri to be appended
        :param args: list<str>: / split parts of a uri to be appended to url
        :return: response: The results of the get request (the page)
        """
        uri = '{0}/{1}'.format(self.url, '/'.join(args))
        return (self.session.get(uri))

    def get_page_root(self, page):
        """
        Get the root element of the supplied page
        :param page: response: the page from which to get the root
        :return:  ElementTree: the root of the page
        """
        return (etree.HTML(page.content))

    def post(self, **kwargs):
        """
        Send a post request using the current session
        :param kwargs: dict: request data to be sent
        :return:
        """
        page = self.session.post(url=self.url, data=kwargs)
        return (page)

    def populate_list(self, list_name):
        """
        Populate a single MailingList object by calling its update method
        :param list_name: str: the name of the list to update
        :return:
        """
        self.lists[list_name].update()

    def populate_all(self):
        """
        Populate all lists by calling their update methods
        :return:
        """
        page = self.get_page()
        if self.__logged_in(page):
            self.__populate_all(page)
        else:
            print("Cannot populate lists, not logged in!", file=stderr)

    def logged_in(self):
        """
        Check if currently logged in
        :return: bool: whether or not the current session is logged in
        """
        return (self.__logged_in(self.get_page()))

    def log_in(self, email, password, populate=False):
        """
        Log in using email and password, optionally, populate all lists
        :param email: str: the log in email address for sympa
        :param password: str: the password for the log in email address
        :param populate: bool: whether or not to populate all lists on log in
        :return:
        """
        # Post login action, using the following data:
        login_request = {'action': 'login',
                         'email': '{}'.format(email),
                         'passwd': '{}'.format(password)}
        login = self.post(**login_request)

        if not self.__logged_in(login):
            print('Unable to log in...', file=stderr)
        else:
            # Get the list names regardless of population
            self.__get_list_names(login)

            if populate:
                # populate all lists for this user
                self.__populate_all_lists()

    def log_out(self):
        """
        Log out of the current session
        :return:
        """
        self.post(action='logout')

    def close(self):
        """
        Close the connection of the current session
        :return:
        """
        self.post(body={}, headers={'Connection': 'close'})
