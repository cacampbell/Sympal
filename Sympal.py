#!/usr/bin/env python3
from datetime import datetime
from datetime import timedelta
from lxml import etree
from os import environ
from os.path import isfile
from queue import Queue
import requests
from sys import stderr
from threading import Thread
from unittest import TestCase
from unittest import TestLoader
from unittest import TextTestRunner


class Sympa:
    # looked at Sympa page source to determine this information after login
    LISTS_XPATH = etree.XPath('//*[@id="Menus"]/div[3]/ul/li/a/@href')
    MAX_CONCURRENT_REQUEST_THREADS = 4

    def __enter__(self):
        return(self)

    def __exit__(self, ex_type, ex_val, traceback):
        self.log_out()
        self.close()

    def __init__(self, url):
        self.url = url
        self.session = requests.session()
        self.lists = {}

    def _logged_in(self, page):
        return('action_logout' in page.text)

    def post(self, **kwargs):
        page = self.session.post(url=self.url, data=kwargs)
        return(page)

    def get_page(self, *args):
        uri = '{0}/{1}'.format(self.url, '/'.join(args))
        return(self.session.get(uri))

    def get_page_root(self, page):
        return(etree.HTML(page.content))

    def __populate_all_lists(self):
        concurrent = self.MAX_CONCURRENT_REQUEST_THREADS
        q = Queue(concurrent * 2)

        def populate():
            while True:
                name = q.get()
                self.lists[name].update()
                q.task_done()

        for i in range(concurrent):
            t = Thread(target=populate)
            t.daemon = True
            t.start()

        for name, l in self.lists.items():
            q.put(name)

        q.join()

    def populate_list(self, list_name):
        self.lists[list_name].update()

    def populate_all(self):
        page = self.get_page()
        if self._logged_in(page):
            self.__populate_all(page)
        else:
            print("Cannot populate lists, not logged in!", file=stderr)

    def __populate_all(self, page):
        self.__get_list_names(page)
        self.__populate_all_lists()

    def __get_list_names(self, page):
        root = self.get_page_root(page)
        links = self.LISTS_XPATH(root)
        names = (link.rsplit('/', 1)[1] for link in links)
        self.lists = {}

        for name in names:
            self.lists[name] = MailingList(self, name)

    def logged_in(self):
        return(self._logged_in(self.get_page()))

    def log_in(self, email, password, populate=False):
        # 302 found when logged in, 200 when not but site is working
        login = self.post(action='login', email=email, passwd=password)

        if not self._logged_in(login):
            print('Unable to log in...', file=stderr)
        else:
            self.__get_list_names(login)

            if populate:
                self.__populate_all_lists()

    def log_out(self):
        self.post(action='logout')

    def close(self):
        self.post(body={}, headers={'Connection': 'close'})


class MailingList_Meta(type):
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
        """
        def check_populated_before_exec(self, *args, **kwargs):
            self.update()
            if self._owner:
                return(func(self, *args, **kwargs))
            else:
                print(cls.AUTHMSG.format(self.name), file=stderr)
                return(None)

        return(check_populated_before_exec)

    def __new__(cls, name, bases, attrs):
        """
        Wrap the listed attributes of the MailingList class with checks for
        ownership.
        """
        for m in cls.ADMIN_METHODS:
            if m in attrs:
                attrs[m] = cls.create_check_populated_before_exec(attrs[m])

        return(type.__new__(cls, name, bases, attrs))


class MailingList(object, metaclass=MailingList_Meta):
    PRIV_ROLES = ['Privileged owner',
                  'Owner',
                  'Moderator',
                  'Privileged moderator']
    PRIV_XPATH = etree.XPath('//*[@id="Identity"]/text()')
    # About <tbody/> tags:
    # http://stackoverflow.com/questions/18241029/why-does-my-xpath-query-
    # scraping-html-tables-only-work-in-firebug-but-not-the
    # http://stackoverflow.com/questions/1678494/why-does-firebug-add-
    # tbody-to-table/1681427#1681427
    SUBSCRIBERS_XPATH = etree.XPath(('//*[@id="Paint"]/div[4]/div/form[4]'
                                    '/fieldset/table'))
    ALT_XPATH = etree.XPath(('//*[@id="Paint"]/div[4]/div[2]/form[5]/'
                            'fieldset/table'))
    BOUNCING_XPATH = etree.XPath(('//*[@id="Paint"]/div[4]/form[4]/'
                                 'fieldset/table'))

    UPDATE_MINS = 5

    def __init__(self, sympa, name):
        self.sympa = sympa
        self.name = name
        self._owner = False
        self._subscribers = {}
        self.review_uri = ('?sortby=email&action='
                           'review&list={}&size=1000').format(self.name)
        self.review_bouncing_uri = ('?sortby=email&action=reviewbouncing&'
                                    'list={}&size=1000').format(self.name)
        self.review = None
        self.review_bouncing = None
        self._last_updated = datetime.now()

    def __repr__(self):
        return("<MailingList '{}'>".format(self.name))

    def __needs_update(self):
        difference = datetime.now() - self._last_updated
        outdated = (difference > timedelta(minutes=self.UPDATE_MINS))
        update = \
            not self.review or \
            not self._subscribers or \
            not self.review_bouncing or \
            outdated
        return(update)

    def update(self):
        if self.__needs_update():
            self.__get_review()
            self.__get_review_bouncing()
            self.__check_ownership()
            self.__update_subscribers()

    def __update_subscribers(self):
        self.__update_non_bouncing_subscribers()
        self.__update_bouncing()
        self._last_updated = datetime.now()

    def check_owner(self):
        page = self.review
        priv = self.PRIV_XPATH(self.sympa.get_page_root(page))
        if any(x in priv[1] for x in self.PRIV_ROLES):
            return(True)

        return(False)

    def __check_ownership(self):
        self._owner = self.check_owner()

    def __get_review(self):
        self.review = self.sympa.get_page(self.review_uri)

    def __get_review_bouncing(self):
        self.review_bouncing = self.sympa.get_page(self.review_bouncing_uri)

    def __update_non_bouncing_subscribers(self):
        page = self.review
        page_root = self.sympa.get_page_root(page)
        self.__update_subscribers_from_root(page_root)

    def __update_bouncing(self):
        page = self.review_bouncing
        page_root = self.sympa.get_page_root(page)
        self.__update_bouncing_from_root(page_root)

    def __update_subscriber_bouncing_info(self, list_of_trs):
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

        for tr in list_of_trs:
            info = tr_to_subscriber_info(tr)
            self._subscribers[info['email']].update_bouncing_info(**info)

    def __update_bouncing_from_root(self, page_root):
        rows = None

        try:
            # Header of this table is actually in a form, with two rows of
            # table headers, and 5 columns of stats relating to bouncing emails
            rows = self.BOUNCING_XPATH(page_root)[0].findall('tr')[2:]
        except IndexError:
            if not self._owner:
                print(MailingList_Meta.AUTHMSG.format(self.name))
            else:
                print("List '{}' has no bouncing subscriptions".format(
                    self.name), file=stderr)

        if rows:
            self.__update_subscriber_bouncing_info(rows)

    def __rows_to_Subscribers(self, list_of_trs):
        subscribers = []

        def tr_to_subscriber_dict(tr):
            columns = tr.findall('td')
            if len(columns) == 9:  # status notification
                columns.pop(3)

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
            d['bouncing'] = False
            d['bounce_score'] = 'no score'
            d['bounce_count'] = 0
            d['first_bounce'] = None
            d['last_bounce'] = None
            return(d)

        for tr in list_of_trs:
            subscribers += [Subscriber(**tr_to_subscriber_dict(tr))]

        return(subscribers)

    def __update_subscribers_from_root(self, page_root):
        rows = None

        try:
            rows = self.SUBSCRIBERS_XPATH(page_root)[0].findall('tr')[1:]
        except IndexError:
            try:
                rows = self.ALT_XPATH(page_root)[0].findall('tr')[1:]
            except IndexError:
                if not self._owner:
                    print(MailingList_Meta.AUTHMSG.format(self.name))
                else:
                    print("List '{}' has no subscriptions".format(self.name),
                          file=stderr)

        if rows:
            self.__set_updated_subscribers(self.__rows_to_Subscribers(rows))
        else:
            self.__set_updated_subscribers([])

    def get_subscribers_email_list(self, filename=None):
        """Returns the list of subscriber emails, can write list to a file
        :param: filename: str: name of file to write subscriber list
        :return: list: list of subscriber emails
        """
        # page = self.sympa.get_page('dump', self.name, 'light')
        # subscribers = [x for x in page.text.split('\n') if x is not '']
        subscribers = self.get_subscribers().keys()

        if filename:
            with open(filename, 'w+') as subscriber_list:
                for email in subscribers.keys():
                    print(email, file=subscriber_list)

        return(subscribers)

    def get_subscribers(self):
        """
        Get a list of Subscribers for this MailingList
        :return: list<Subscriber>: the subscriber list
        """
        return(self._subscribers)

    def get_bouncing_email_list(self, filename=None):
        """
        Return a list of emails (str), can be written to file
        :filename: str: the name of the file to write to
        :return: list: the list of emails
        """
        subscribers = self.get_bouncing().keys()

        if filename:
            with open(filename, 'w+') as bouncing_list:
                for email in subscribers.keys():
                    print(email, file=bouncing_list)

        return(subscribers)

    def get_bouncing(self):
        """
        Get a list of bouncing Subscribers for this MailingList
        :return: list<Subscriber>: the bouncing subscribers
        """
        # Each email:subscriber pair if that subscriber is bouncing
        return({e: s for e, s in self._subscribers.items() if s.bouncing})

    def __reset_bouncing_request(self, email):
        """
        Generate a request to reset a user's bouncing status
        :param: email: str: email address for the subscriber
        """
        data = {'list': '{}'.format(self.name),
                'previous_action': 'reviewbouncing',
                'email': '{}'.format(email),
                'action_resetbounce': 'Reset errors for selected users'}
        return(data)

    def reset_bouncing(self):
        """
        Reset email addresses that are bouncing for this MailingList
        """
        requests = []

        for email in self.get_bouncing().keys():
            reset_request = self.__reset_bouncing_request(email)
            requests += [reset_request]

        self.__send_concurrent_requests(requests)
        self.__update_bouncing()

    def reset_bouncing_subscriber(self, email):
        """
        Reset one subscriber whose address is bouncing
        :param: email: str: email address for the subscriber to reset
        """
        data = self.__reset_bouncing_request(email)
        response = self.sympa.post(**data)
        self.__update_bouncing()
        return(response)

    def remove_bouncing_subscribers(self):
        """
        Remove subscribers that are bouncing from the list
        """
        bouncing = self.get_bouncing().keys()
        requests = []

        for subscriber in bouncing:
            requests += [self.__remove_subscriber_request(subscriber)]

        self.__send_concurrent_requests(requests)
        self.__update_subscribers()

    def __set_updated_subscribers(self, subscribers):
        # __subs_from_obj returns a dictionary of email: Subscriber pairs
        self._subscribers = self.__sub_d(self.__subs_from_obj(subscribers))

    def set_subscribers(self, subscribers):
        """
        Update this MailingList and Sympa to a new subscriber list

        Compares the given subscriber list to the current updated list and
        determines requests that must be made to make the current list match
        the provided list (in terms of Subscriber identity)
        :param: subscribers: obj: Mixed objects signifying Subscribers
        """
        # Convert possible input objects to dict<Subscriber>
        subscribers = self.__sub_d(self.__subs_from_obj(subscribers).values())
        # get just the input emails
        emails = [x.email for x in subscribers]
        # Get just the emails from the current subscriptions
        self_emails = [x.email for x in self._subscribers.values()]
        # S in input list, but S not in current list, so add S to current
        a = [x for x in subscribers if x.email not in self_emails]
        # S in current list, but S not in input list, so remove S from current
        d = [x for x in self._subscribers.values() if x.email not in emails]
        # Formulate requests for Subscribers to be added to the current
        add_requests = [self.__add_subscriber_request(x) for x in a]
        # Formulate deletion requests for Subscribers to be removed from current
        del_requests = [self.__remove_subscriber_request(x) for x in d]
        # combine this list into one list of requests
        requests = add_requests + del_requests
        # determine the number of concurrent requests and make a Queue
        self.__send_concurrent_requests(requests)
        self.update()

    def __send_concurrent_requests(self, requests):
        concurrent = self.sympa.MAX_CONCURRENT_REQUEST_THREADS
        q = Queue(concurrent * 2)

        def worker():
            # Worker posts the request
            while True:
                data = q.get()
                self.sympa.post(**data)
                q.task_done()

        # create a number of workers equal to the concurrency limit, start them
        for i in range(concurrent):
            t = Thread(target=worker)
            t.daemon = True
            t.start()

        # Send requests to the queue to be executed by workers
        for request in requests:
            q.put(request)

    def __subs_from_list(self, subscribers):
        """
        Convert a mixed list into a list of Subscribers
        :param: subscribers: list: a list of strings, Subscribers
        :return: list<Subscriber>: The converted list of Subscribers
        """
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
                    print("Could not parse subscriber item: {}".format(item))
            elif type(item) is str:
                s = Subscriber(email=item[0],
                               mailing_list=self)
                new_subscriber_list += [s]
            else:
                print("Could not parse subscriber item: {}".format(item))

        return(new_subscriber_list)

    def __subs_from_dict(self, subscribers):
        """
        Convert a dictionary into a list of Subscribers, assuming email: name
        pairs compose the dictionary, or rather <str>: <str> pairs
        :param: subscribers: dict: a dictionary of subscribers
        :return: list<Subscriber>: The converted list of Subscribers
        """
        new_subscriber_list = []

        for email, name in subscribers.items():
            s = Subscriber(email=email, name=name, mailing_list=self)
            new_subscriber_list += [s]

        return(new_subscriber_list)

    def __subs_from_file(self, subscribers):
        """
        read a file and extract <str> email: <str> name pairs, then create a
        list of Subscribers from it
        :param: subscribers: str: filename to be read
        :return: list<Subscriber>: The Subscriber list
        """
        new_subscriber_list = []

        with open(subscribers, 'r+') as f_h:
            for line in f_h.readlines():
                chunks = line.split()
                email = chunks[0].strip()
                name = ""

                if len(chunks) == 2:
                    name = " ".join(chunks[1:]).strip()

                s = Subscriber(email=email, name=name, mailing_list=self)
                new_subscriber_list += [s]

        return(new_subscriber_list)

    def __sub_d(self, list_of_Subscribers):
        dictionary = {}

        for sub in list_of_Subscribers:
            dictionary[sub.email] = sub

        return(dictionary)

    def __subs_from_obj(self, subscribers):
        """
        :param: subscribers: list,dict,str: a list of emails, a list of
        subscribers, a dictionary of <email>:<name> pairs, or a file containing
        rows of "<email> <name>"
        """
        if type(subscribers is list):
            if all([type(x) is Subscriber for x in subscribers]):
                return(subscribers)
            else:
                return(self.__subs_from_list(subscribers))
        elif type(subscribers is dict):
            if all([type(x) is Subscriber for x in subscribers.values()]):
                return(subscribers.values())
            else:
                return(self.__subs_from_dict(subscribers))
        elif type(subscribers) is str:
            if isfile(subscribers):
                return(self.__subs_from_file(subscribers))

        return([])

    def __add_subscriber_request(self, email, real_name=""):
        data = {'list': '{}'.format(self.name),
                'action_add': 'Add subscribers',
                'quiet': 'on',
                'used': 'true',
                'dump': '{} {}'.format(email, real_name).strip()
                }
        return(data)

    def add_subscriber(self, email, real_name=""):
        data = self.__add_subscriber_request(email, real_name)
        response = self.sympa.post(**data)
        self.__update_subscribers()
        return(response)

    def __remove_subscriber_request(self, email):
        data = {'list': '{}'.format(self.name),
                'quiet': 'on',
                'email': '{}'.format(email),
                'action_del': 'Delete selected email addresses'
                }
        return(data)

    def remove_subscriber(self, email):
        data = self.__remove_subscriber_request(email)
        response = self.sympa.post(**data)
        self.__update_subscribers()
        return(response)


class Subscriber:
    """
    Storage class for attributes relating to a subsriber.
    """
    subscriber_info = ['email', 'name', 'picture', 'reception', 'sources',
                       'sub_date', 'last_update', 'mailing_list']
    bouncing_info = ['bouncing', 'bounce_score', 'bounce_count', 'first_bounce',
                     'last_bounce']
    recognized_attrs = subscriber_info + bouncing_info

    def __set_attributes(self, given_dict, allowed_keys):
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
        try:
            assert('email' in kwargs.keys())
            assert('mailing_list' in kwargs.keys())
        except AssertionError:
            print("Subscriber requires 'email' and 'mailing_list' arguments",
                  file=stderr)
            raise

        self.__set_attributes(kwargs, self.recognized_attrs)

    def update_subscriber_info(self, **kwargs):
        self.__set_attributes(kwargs, self.subscriber_info)

    def update_bouncing_info(self, **kwargs):
        self.__set_attributes(kwargs, self.bouncing_info)

    def __repr__(self):
        return("<Subscriber '{}' of '{}'>".format(self.email,
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
                for email, sub in bouncing.items():
                    print("Email: {}, Name: {}".format(email, sub.name))

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

    def tearDown(self):
        self.sympa.log_out()
        self.sympa.close()


if __name__ == "__main__":
    suite = TestLoader().loadTestsFromTestCase(Test_Sympa_MailingList)
    TextTestRunner(verbosity=3).run(suite)
