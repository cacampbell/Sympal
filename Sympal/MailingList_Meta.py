#!/usr/bin/env python3
from sys import stderr


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
                return (func(self, *args, **kwargs))
            else:  # No admin privileges -- don't make requests, return None
                print(cls.AUTHMSG.format(self.name), file=stderr)
                return (None)

        return (check_populated_before_exec)

    def __new__(cls, name, bases, attrs):
        # When a new instance of MailingList is created, wrap the attributes
        # of that instance if they are in the list of attributes to wrap (if
        # they require updated subscribers and admin privileges)
        for m in cls.ADMIN_METHODS:
            if m in attrs:
                attrs[m] = cls.create_check_populated_before_exec(attrs[m])

        return (type.__new__(cls, name, bases, attrs))
