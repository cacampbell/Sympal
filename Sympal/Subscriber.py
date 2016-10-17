#!/usr/bin/env python3
from sys import stderr


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
            assert ('email' in kwargs.keys())
            assert ('mailing_list' in kwargs.keys())
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
