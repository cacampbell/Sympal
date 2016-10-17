#!/usr/bin/env python3
from datetime import datetime
from datetime import timedelta
from os import environ
from os.path import isfile
from queue import Queue
from sys import stderr
from threading import Thread
from time import sleep
from unittest import TestCase
from unittest import TestLoader
from unittest import TextTestRunner

import requests
from lxml import etree


class Sympa:
    # XPath for the 'list of lists' on sympa home page
    LISTS_XPATH = etree.XPath('//*[@id="Menus"]/div[3]/ul/li/a/@href')
    MAX_CONCURRENT_REQUEST_THREADS = 4

    def __enter__(self):
        return(self)

    def __init__(self, url):
        self.url = url
        self.session = requests.session()
        self.lists = {}

    def __exit__(self, ex_type, ex_val, traceback):
        self.log_out()
        self.close()

    def __logged_in(self, page):
        # Check a page for the ability to log out -- signifying logged in
        return('action_logout' in page.text)

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
        return(self.__logged_in(self.get_page()))

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


class MailingList_Meta(type):
    # The methods that require the user to be both logged in and have admin
    # privileges for the list instance
    ADMIN_METHODS = ['get_subscribers_email_list',
                     'get_bouncing_email_list',
                     'get_subscribers',
                     'get_bouncing',
                     'set_subscribers',
                     'add_subscriber',
                     'remove_subscriber',
                     'reset_bouncing',
                     'reset_bouncing_subscriber',
                     'remove_bouncing_subscribers']

    AUTHMSG = ("The current user is not an administrator of the list '{}'. "
               "Access Denied.")

    @classmethod
    def create_check_populated_before_exec(cls, func):
        """
        A wrapper for methods of a MailingList instance to prevent those
        methods from running if the current user of the parent Sympa instance
        does not have admin / mod access to the current list information
        :return: func: wrapped function that checks instance ownership and then
        performs the original action of the method.
        :param func: function: the method to be wrapped
        :return: function: the wrapped function
        """
        def check_populated_before_exec(self, *args, **kwargs):
            """
            Check that the subscribers have been fully populated and that the
            user is an administrator for this list instance.
            :param self: MailingList: this
            :param args: list: positional arguments
            :param kwargs: dict: keyword arguments
            :return:
            """
            # First update the given list, to populate subscribers, and check
            # the ownership
            self.update()

            if self._admin:  # Current user has admin privileges on the list
                return(func(self, *args, **kwargs))
            else:  # No admin privileges -- don't make requests, return None
                print(cls.AUTHMSG.format(self.name), file=stderr)
                return(None)

        return(check_populated_before_exec)

    def __new__(cls, name, bases, attrs):
        # When a new instance of MailingList is created, wrap the attributes
        # of that instance if they are in the list of attributes to wrap (if
        # they require updated subscribers and admin privileges)
        for m in cls.ADMIN_METHODS:
            if m in attrs:
                attrs[m] = cls.create_check_populated_before_exec(attrs[m])

        return(type.__new__(cls, name, bases, attrs))


class MailingList(object, metaclass=MailingList_Meta):
    # Roles that signify admin privileges (I think)
    PRIV_ROLES = ['Privileged owner',
                  'Owner',
                  'Moderator',
                  'Privileged moderator']
    # XPath for the role of the current user
    PRIV_XPATH = etree.XPath('//*[@id="Identity"]/text()')
    # About <tbody/> tags:
    # http://stackoverflow.com/questions/18241029/why-does-my-xpath-query-
    # scraping-html-tables-only-work-in-firebug-but-not-the
    # http://stackoverflow.com/questions/1678494/why-does-firebug-add-
    # tbody-to-table/1681427#1681427
    #
    # Xpath for the table of subscribers on the review page
    SUBSCRIBERS_XPATH = etree.XPath(('//*[@id="Paint"]/div[4]/div/form[4]'
                                    '/fieldset/table'))
    # But, if there is a notification at the top of the form containing the
    # review subscribers table, then this is the XPath for that table
    ALT_XPATH = etree.XPath(('//*[@id="Paint"]/div[4]/div[2]/form[5]/'
                            'fieldset/table'))
    # On review bouncing page, the table containing bouncing info XPath...
    BOUNCING_XPATH = etree.XPath(('//*[@id="Paint"]/div[4]/form[4]/'
                                 'fieldset/table'))

    # How frequently to update the MailingList instances in minutes
    UPDATE_MINS = 5
    TIMEOUT = 60
    FREQUENCY = 10

    def __init__(self, sympa, name):
        self.sympa = sympa
        self.name = name
        self._admin = False
        self._subscribers = {}
        # URI for subscribers and bouncing, showing up to 10,000 members
        self.review_uri = ('?sortby=email&action='
                           'review&list={}&size=10000').format(self.name)
        self.review_bouncing_uri = ('?sortby=email&action=reviewbouncing&'
                                    'list={}&size=10000').format(self.name)
        self.review = None
        self.review_bouncing = None
        self._last_updated = datetime.now()

    def __repr__(self):
        return("<MailingList '{}'>".format(self.name))

    def __needs_update(self):
        # If this instance needs to be updated, which is when:
        # It hasn't been updated in the last UPDATE_MINS,
        # There is no subscribers page,
        # There is no bouncing page,
        # The subscribers list == None (not initialized)
        difference = datetime.now() - self._last_updated
        outdated = (difference > timedelta(minutes=self.UPDATE_MINS))
        update = \
            self.review is None or \
            not self._subscribers or \
            not self.review_bouncing or \
            outdated
        return(update)

    def update(self):
        # Update this instance if it needs to be updated
        if self.__needs_update():
            self.__get_review()  # Update review page
            self.__get_review_bouncing()  # Update review bouncing page
            self.__check_admin()  # Update admin privileges
            self.__update_subscribers()  # Update subscriber list

    def __update_subscribers(self, wait_for_update=False):
        # Get all of the subscribers, populate listed information, then, fill
        # in information obtained from the review bouncing page, set last update
        self.__update_from_review(wait_for_update)
        self.__update_from_review_bouncing(wait_for_update)
        self._last_updated = datetime.now()

    def check_admin(self):
        # Check admin privileges
        page = self.review
        priv = self.PRIV_XPATH(self.sympa.get_page_root(page))
        if any(x in priv[1] for x in self.PRIV_ROLES):
            return(True)

        return(False)

    def __check_admin(self):
        # Update stored admin privileges
        self._admin = self.check_admin()

    def __get_review(self):
        # Get the review page for this list
        self.review = self.sympa.get_page(self.review_uri)

    def __get_review_bouncing(self):
        # Get the review bouncing page for this list
        self.review_bouncing = self.sympa.get_page(self.review_bouncing_uri)

    def __update_from_review(self, wait_for_update=False):
        # Get the subscribers from the review page, update information
        page = self.review

        if wait_for_update:
            # yes, timeout will be slightly less than expected, thats okay
            freq = timedelta(seconds=self.FREQUENCY)
            timeout = datetime.now() + timedelta(seconds=self.TIMEOUT)

            while datetime.now() < timeout:
                self.__get_review()
                if self.review.text != page.text:  # compare page text
                    break
                sleep(freq.total_seconds())

        page_root = self.sympa.get_page_root(self.review)
        self.__update_subscribers_from_root(page_root)

    def __update_from_review_bouncing(self, wait_for_update=False):
        # Get information from the review bouncing page, update subscribers
        page = self.review_bouncing

        if wait_for_update:
            # yes, timeout will be slightly less than expected, thats okay
            freq = timedelta(seconds=self.FREQUENCY)
            timeout = datetime.now() + timedelta(seconds=self.TIMEOUT)

            while datetime.now() < timeout:
                self.__get_review_bouncing()
                if self.review != page:  # nested comparison handled by python
                    break
                sleep(freq.total_seconds())

        page_root = self.sympa.get_page_root(self.review_bouncing)
        self.__update_bouncing_from_root(page_root)

    def __update_subscriber_bouncing_info(self, list_of_trs):
        # Parse information from the table on the review bouncing page
        def tr_to_subscriber_info(tr):
            # See the following for datetime formatting:
            # https://docs.python.org/2/library/datetime.html#
            # strftime-datetime.strptime-behavior
            columns = tr.findall('td')
            d = {}
            d['email'] = columns[1][0].text.strip()
            d['bouncing'] = True
            d['bounce_score'] = columns[2].text.strip()
            d['bounce_count'] = columns[3].text.strip()
            d['first_bounce'] = datetime.strptime(columns[4].text.strip(),
                                                  "%d %b %Y")
            d['last_bounce'] = datetime.strptime(columns[5].text.strip(),
                                                 "%d %b %Y")
            return(d)

        d = {}
        d['bouncing'] = False
        d['bounce_score'] = 'no score'
        d['bounce_count'] = 0
        d['first_bounce'] = None
        d['last_bounce'] = None

        # Initialize bouncing info for each subscriber
        for subscriber in self._subscribers.values():
            subscriber.update_bouncing_info(**d)

        for tr in list_of_trs:
            # For each row of the bouncing subscribers table
            info = tr_to_subscriber_info(tr)
            self._subscribers[info['email']].update_bouncing_info(**info)

    def __update_bouncing_from_root(self, page_root):
        # From the root of a page, find the rows of the bouncing subscribers
        # table, and send that to be parsed, added to subscribers
        rows = None

        try:
            # Header of this table is actually in a form, with two rows of
            # table headers, and 5 columns of stats relating to bouncing emails
            rows = self.BOUNCING_XPATH(page_root)[0].findall('tr')[2:]
        except IndexError:  # Could not find this element on the page
            if not self._admin:
                print(MailingList_Meta.AUTHMSG.format(self.name), file=stderr)
            else:
                print("List '{}' has no bouncing subscriptions".format(
                    self.name), file=stderr)

        if rows:
            self.__update_subscriber_bouncing_info(rows)

    def __rows_to_Subscribers(self, list_of_trs):
        # Parse the table of subscribers from the review page of this list
        def tr_to_subscriber_dict(tr):
            columns = tr.findall('td')
            if len(columns) == 9:  # status notification for a user
                columns.pop(3)  # Remove status notification

            d = {}
            d['email'] = columns[1][0].text.strip()
            d['picture'] = columns[2]
            d['name'] = columns[3].findall('span')[0].text.strip()
            d['reception'] = columns[4].text.strip()
            d['sources'] = columns[5].text.strip()
            d['sub_date'] = datetime.strptime(columns[6].text.strip(),
                                              "%d %b %Y")
            d['last_update'] = datetime.strptime(columns[7].text.strip(),
                                                 "%d %b %Y")
            d['mailing_list'] = self
            # Set bouncing info to default values for now
            d['bouncing'] = False
            d['bounce_score'] = 'no score'
            d['bounce_count'] = 0
            d['first_bounce'] = None
            d['last_bounce'] = None
            return(d)

        found_emails = []  # Keep track of the email addresses found
        extant = True  # Assume subscribers not empty to start

        if not self._subscribers:
            extant = False  # was empty at start, actually
            self._subscribers = {}  # Initialize it, in case it was None

        for tr in list_of_trs:
            # For each row, if there is an existing subscriber, update it,
            # otherwise, create a new subscriber and add it.
            data = tr_to_subscriber_dict(tr)
            found_emails += [data['email']]

            if data['email'] in self._subscribers.keys():
                self._subscribers[data['email']].update_subscriber_info(**data)
                # Do not updating bouncing information (with defaults)
            else:
                self._subscribers[data['email']] = Subscriber(**data)

        if extant:  # The subscriber list was not empty at start of update
            # Remove Subscribers that were not found on the review page
            for email in list(self._subscribers.keys()):
                if email not in found_emails:
                    self._subscribers.pop(email)

    def __update_subscribers_from_root(self, page_root):
        # Update the subscribers of this MailingList from page root
        rows = []

        try:
            # Table of subscribers
            rows = self.SUBSCRIBERS_XPATH(page_root)[0].findall('tr')[1:]
        except IndexError:
            try:
                # If notification on form, then this is the table instead
                rows = self.ALT_XPATH(page_root)[0].findall('tr')[1:]
            except IndexError:
                if not self._admin:
                    print(MailingList_Meta.AUTHMSG.format(self.name),
                          file=stderr)
                else:
                    print("List '{}' has no subscriptions".format(self.name),
                          file=stderr)

        self.__rows_to_Subscribers(rows)

    def get_subscribers_email_list(self, filename=None):
        # User the subscriber dictionary to print a list of emails
        # Alternatively, can use the following:
        # page = self.sympa.get_page('dump', self.name, 'light')
        # subscribers = [x for x in page.text.split('\n') if x is not '']
        subscribers = list(self.get_subscribers().keys())

        if filename:
            with open(filename, 'w+') as subscriber_list:
                for email in subscribers:
                    print(email, file=subscriber_list)

        return(subscribers)

    def get_subscribers(self):
        """
        Get the subscriber dictionary
        :return: dict<Subscriber>: the subscriber dictionary
        """
        return(self._subscribers)

    def get_bouncing_email_list(self, filename=None):
        """
        The a list of bouncing email addresses
        :param filename: str: write list to this file
        :return: list<str>: list of subscriber emails
        """
        subscribers = list(self.get_bouncing().keys())

        if filename:
            with open(filename, 'w+') as bouncing_list:
                for email in subscribers:
                    print(email, file=bouncing_list)

        return(subscribers)

    def get_bouncing(self):
        """
        Get the dictionary of Bouncing subscribers
        :return: dict<Subscriber>: The bouncing subscribers
        """
        # Each email:subscriber pair if that subscriber is bouncing
        return({e: s for e, s in self._subscribers.items() if s.bouncing})

    def __reset_bouncing_request(self, email):
        """
        Generate data for request to reset the bouncing email address
        :param email: str: email address to reset
        :return: dict: data for request
        """
        data = {'list': '{}'.format(self.name),
                'previous_action': 'reviewbouncing',
                'email': '{}'.format(email),
                'action_resetbounce': 'Reset errors for selected users'}
        return(data)

    def __send_concurrent_requests(self, requests):
        # Sends concurrent requests through the session using the predefined
        # max concurrent threads
        concurrent = self.sympa.MAX_CONCURRENT_REQUEST_THREADS  # concurrent lim
        q = Queue(concurrent * 2)  # queue twice as large as number of threads
        threads = []

        def worker():
            # Worker posts the request
            while True:
                data = q.get()  # Request data from some __request method

                if data is None:
                    break

                self.sympa.post(**data)  # Post this request
                q.task_done()

        # create a number of workers equal to the concurrency limit, start them
        for i in range(concurrent):
            t = Thread(target=worker)
            t.start()
            threads += [t]

        # Send requests to the queue to be executed by workers
        for request in requests:
            q.put(request)

        # Wait for all tasks to be done
        q.join()

        # stop workers
        for i in range(concurrent):
            q.put(None)

        for t in threads:
            t.join()

    def reset_bouncing(self):
        """
        Reset the bouncing email addresses for this list
        :return:
        """
        requests = []

        for email in self.get_bouncing().keys():
            reset_request = self.__reset_bouncing_request(email)
            requests += [reset_request]

        self.__send_concurrent_requests(requests)
        self.__update_from_review_bouncing(wait_for_update=True)

    def reset_bouncing_subscriber(self, email):
        """
        Reset a single bouncing subscriber
        :param email: str: email to reset
        :return: response: the result of the reset request
        """
        data = self.__reset_bouncing_request(email)  # Data to be sent
        response = self.sympa.post(**data)  # Post the data
        self.__update_from_review_bouncing(wait_for_update=True)
        return(response)

    def remove_bouncing_subscribers(self):
        """
        Delete all bouncing email addresses from the list
        :return:
        """
        bouncing = list(self.get_bouncing().keys())  # list of email adddresses
        requests = []

        for subscriber in bouncing:  # Add a request to the list for each email
            requests += [self.__remove_subscriber_request(subscriber)]

        self.__send_concurrent_requests(requests)  # send all requests
        self.__update_subscribers(wait_for_update=True)  # Update

    def set_subscribers(self, sub_obj):
        """
        Set the subscribers for the current list. First, determine which email
        addresses must be added, then determine which need to be removed. For
        each of these email addresses (and actions), generate a request. Then,
        send the requests concurrently.
        :param subscribers: obj: something convertible to dict<Subscriber>
        :return:
        """
        def __to_dict(x):
            return {'email': x.email, 'real_name': x.name}

        # Convert possible input objects to dict<Subscriber>, then get values
        subscribers = self.__subs_from_obj(sub_obj)
        subscribers_list = list(subscribers.values())
        # get just the input emails
        emails = [x.email for x in subscribers_list]
        # self email list is keys for subscribers
        self_emails = list(self._subscribers.keys())
        # S in input list, but S not in current list, so add S to current
        add_m = [x for x in emails if x not in self_emails]
        # take a subscriber, return a dict of just the email and name
        additions = [__to_dict(subscribers[x]) for x in add_m]
        # S in current list, but S not in input list, so remove S from current
        deletions = [x for x in self_emails if x not in emails]
        # Formulate requests for Subscribers to be added to the current
        add_requests = [self.__add_subscriber_request(**x) for x in additions]
        # Formulate deletion requests for Subscribers to be removed from current
        del_requests = [self.__remove_subscriber_request(x) for x in deletions]
        # combine this list into one list of requests
        requests = add_requests + del_requests
        # determine the number of concurrent requests and make a Queue
        if requests:
            self.__send_concurrent_requests(requests)
            self.__update_subscribers(wait_for_update=True)

    def __subs_from_list(self, subscribers):
        # Generate a list of subscribers from a possibly mixed list of str and
        # Subscriber
        new_subscriber_list = []

        for item in subscribers:
            if type(item) is Subscriber:
                item.mailing_list = self
                new_subscriber_list += [item]
            elif type(item) is tuple:
                if len(item) == 2 and all(type(x) is str for x in list(item)):
                    s = Subscriber(email=item[0],
                                   name=item[1],
                                   mailing_list=self)
                    new_subscriber_list += [s]
                else:
                    print("Could not parse subscriber item: {}".format(item),
                          file=stderr)
            elif type(item) is str:
                s = Subscriber(email=item,
                               name="",
                               mailing_list=self)
                new_subscriber_list += [s]
            else:
                print("Could not parse subscriber item: {}".format(item),
                      file=stderr)

        return(new_subscriber_list)

    def __subs_from_dict(self, subscribers):
        # Create list<Subscriber> from some dictionary of email: name pairs
        new_subscriber_list = []

        for key, value in subscribers.items():
            if type(key) is str and type(value) is str:
                s = Subscriber(email=key, name=value, mailing_list=self)
                new_subscriber_list += [s]
            elif type(key) is str and type(value) is Subscriber:
                new_subscriber_list += [value]

        return(new_subscriber_list)

    def __subs_from_file(self, subscribers):
        # Parse file of 'email name' lines, and convert them to dict<Subscriber>
        new_subscriber_list = []

        with open(subscribers, 'r+') as f_h:
            for line in f_h.readlines():
                if line is not "":
                    chunks = line.split()
                    email = chunks[0].strip()  # [email] First Last
                    name = ""

                    if len(chunks) >= 2:  # IF email First Last
                        name = " ".join(chunks[1:]).strip()  # email [Name Name]

                    s = Subscriber(email=email, name=name, mailing_list=self)
                    new_subscriber_list += [s]

        return(new_subscriber_list)

    def __subs_from_obj(self, subscribers):
        # Convert the list of Subscribers to a dictionary
        def __sub_d(list_of_Subscribers):
            dictionary = {}

            for sub in list_of_Subscribers:
                dictionary[sub.email] = sub

            return (dictionary)

        # Early versions parsed the subscribers into a list, rather than a dict,
        # and this function used to be the top level method that would handle
        # incoming data. Rather than changing this handling, I just added
        # a step to convert this list to a dictionary -- yes, this will result
        # in a dictionary being converted to a list and back to a dictionary in
        # some cases -- but it also handles ill formed dictionaries as well
        def sub_list(subs):
            if type(subs) is list:
                if all([type(x) is Subscriber for x in subs]):
                    return (subs)
                else:
                    return (self.__subs_from_list(subs))
            elif type(subs) is dict:
                if all([type(x) is Subscriber for x in subs.values()]):
                    return (subs.values())
                else:
                    return (self.__subs_from_dict(subs))
            elif type(subs) is str:
                if isfile(subs):
                    return (self.__subs_from_file(subs))

            return ([])

        return (__sub_d(sub_list(subscribers)))

    def __add_subscriber_request(self, email, real_name=""):
        # Request data for adding a subscriber
        data = {'list': '{}'.format(self.name),
                'action_add': 'Add subscribers',
                'quiet': 'on',
                'used': 'true',
                'dump': '{} {}'.format(email, real_name).strip()
                }
        return(data)

    def add_subscriber(self, email, real_name=""):
        """
        Add a subscriber to this MailingList
        :param email: str: the email address
        :param real_name: str: the real name of the person being added
        :return: response: the response of the request to add
        """
        data = self.__add_subscriber_request(email, real_name)
        response = self.sympa.post(**data)
        self.__update_subscribers(wait_for_update=True)  # Update
        return(response)

    def __remove_subscriber_request(self, email):
        # Request data for removing a subscriber
        data = {'list': '{}'.format(self.name),
                'quiet': 'on',
                'email': '{}'.format(email),
                'action_del': 'Delete selected email addresses'
                }
        return(data)

    def remove_subscriber(self, email):
        """
        Remove a subcriber from this MailingList
        :param email: str: the email address
        :return:
        """
        data = self.__remove_subscriber_request(email)
        response = self.sympa.post(**data)
        self.__update_subscribers(wait_for_update=True)
        return(response)


class Subscriber:
    # Attributes that are expected to belong to each Subscriber
    subscriber_info = ['email', 'name', 'picture', 'reception', 'sources',
                       'sub_date', 'last_update', 'mailing_list']
    # Attributes describing the bouncing status of the Subscriber
    bouncing_info = ['bouncing', 'bounce_score', 'bounce_count', 'first_bounce',
                     'last_bounce']
    # All recognized attributes
    recognized_attrs = subscriber_info + bouncing_info

    def __set_attributes(self, given_dict, allowed_keys):
        # Set attributes of an instance from a dictionary
            for key in allowed_keys:
                if key in given_dict.keys():
                    try:
                        setattr(self, key, given_dict[key])
                    except AttributeError as err:
                        print(str(err), file=stderr)

    def __init__(self, **kwargs):
        """
        Initializes a subscriber
        :param: kwargs: dict: keyword arguments
        expects up to two positional arguments: email, name, which will be
        overidden by keyword arguments, which may include:
            email,
            name,
            picture,
            reception,
            sources,
            sub_date,
            last_update,
            mailing_list,
            bouncing,
            bounce_score,
            bounce_count,
            first_bounce,
            last_bounce
        """
        try:  # Make sure this has an email and a mailing list
            assert('email' in kwargs.keys())
            assert('mailing_list' in kwargs.keys())
        except AssertionError:
            print("Subscriber requires 'email' and 'mailing_list' arguments",
                  file=stderr)
            raise

        self.__set_attributes(kwargs, self.recognized_attrs)

    def update_subscriber_info(self, **kwargs):
        """
        Update subscriber information from a dictionary. Checks the
        supplied dictionary against the class subscriber information
        key list, then updates any parameters that match.
        :param kwargs: dict: parameters to update in this subscriber
        :return:
        """
        self.__set_attributes(kwargs, self.subscriber_info)

    def update_bouncing_info(self, **kwargs):
        """
        Update bouncing information from a dictionary. Checks the supplied
        dictionary against the class bouncing information key list, then
        updates any parameters that match.
        :param kwargs: dict: parameters to update
        :return:
        """
        self.__set_attributes(kwargs, self.bouncing_info)

    def __repr__(self):
        # <subscriber 'user@example.com' of '<MailingList 'example_list'>'>
        return ("<Subscriber '{}' of '{}'>".format(self.email,
                                                   self.mailing_list))


class Test_Sympa_MailingList(TestCase):
    def setUp(self):
        self.sympa = Sympa(environ['sympa_url'])
        self.sympa.log_in(environ['admin_email'], environ['admin_pass'])

    def test_print_lists(self):
        for name, l in self.sympa.lists.items():
            print("Name: {}, List: {}".format(name, l))

    def test_populate_all(self):
        self.sympa.populate_all()

    def test_get_subscribers(self):
        for name, l in self.sympa.lists.items():
            print("Subscribers for list '{}'".format(name))
            subscribers = l.get_subscribers()
            if subscribers:
                for email, sub in subscribers.items():
                    print("Email: {}, Name: {}".format(email, sub.name))

    def test_get_bouncing(self):
        for name, l in self.sympa.lists.items():
            print("Bouncing for list '{}'".format(name))
            bouncing = l.get_bouncing()
            if bouncing:
                print(bouncing)

    def test_get_subscribers_email_list(self):
        for name, l in self.sympa.lists.items():
            print("Subscribers email list for '{}'".format(name))
            email_list = l.get_subscribers_email_list()
            if email_list:
                for email in email_list:
                    print("Email: {}".format(email))

    def test_get_bouncing_email_list(self):
        for name, l in self.sympa.lists.items():
            print("Bouncing email list for '{}'".format(name))
            email_list = l.get_bouncing_email_list()
            if email_list:
                for email in email_list:
                    print("Email: {}".format(email))

    def test_add_subscriber(self):
        subscriber = "cacampbell@ucdavis.edu"
        listname = environ['default_list']
        self.sympa.lists[listname].add_subscriber(subscriber)

    def test_remove_subscriber(self):
        subscriber = "cacampbell@ucdavis.edu"
        listname = environ['default_list']
        self.sympa.lists[listname].remove_subscriber(subscriber)

    def test_set_subscribers(self):
        email_list = environ["test_email_list"]
        self.sympa.lists[environ['default_list']].set_subscribers(email_list)

    def tearDown(self):
        self.sympa.log_out()
        self.sympa.close()


if __name__ == "__main__":
    suite = TestLoader().loadTestsFromTestCase(Test_Sympa_MailingList)
    TextTestRunner(verbosity=3).run(suite)
