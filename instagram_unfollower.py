# python ./unfollow_spree.py -u "yourusername" -p "yourpassword" -settings "settings.json"

import json
import codecs
import datetime
import os.path
import logging
import argparse
from itertools import (filterfalse)

try:
    from instagram_private_api import (
        Client, ClientError, ClientLoginError,
        ClientCookieExpiredError, ClientLoginRequiredError,
        __version__ as client_version)
except ImportError:
    import sys
    sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
    from instagram_private_api import (
        Client, ClientError, ClientLoginError,
        ClientCookieExpiredError, ClientLoginRequiredError,
        __version__ as client_version)


def to_json(python_object):
    if isinstance(python_object, bytes):
        return {'__class__': 'bytes',
                '__value__': codecs.encode(python_object, 'base64').decode()}
    raise TypeError(repr(python_object) + ' is not JSON serializable')


def from_json(json_object):
    if '__class__' in json_object and json_object['__class__'] == 'bytes':
        return codecs.decode(json_object['__value__'].encode(), 'base64')
    return json_object


def onlogin_callback(api, new_settings_file):
    cache_settings = api.settings
    with open(new_settings_file, 'w') as outfile:
        json.dump(cache_settings, outfile, default=to_json)
        print('SAVED: {0!s}'.format(new_settings_file))


if __name__ == '__main__':

    logging.basicConfig()
    logger = logging.getLogger('instagram_private_api')
    logger.setLevel(logging.WARNING)

    parser = argparse.ArgumentParser(
        description='login callback and save settings demo')
    parser.add_argument('-settings', '--settings',
                        dest='settings_file_path', type=str, required=True)
    parser.add_argument('-u', '--username', dest='username',
                        type=str, required=True)
    parser.add_argument('-p', '--password', dest='password',
                        type=str, required=True)
    parser.add_argument('-debug', '--debug', action='store_true')

    args = parser.parse_args()
    if args.debug:
        logger.setLevel(logging.DEBUG)

    print('Client version: {0!s}'.format(client_version))

    device_id = None
    try:

        settings_file = args.settings_file_path
        if not os.path.isfile(settings_file):
            # settings file does not exist
            print('Unable to find file: {0!s}'.format(settings_file))

            # login new
            api = Client(
                args.username, args.password,
                on_login=lambda x: onlogin_callback(x, args.settings_file_path))
        else:
            with open(settings_file) as file_data:
                cached_settings = json.load(file_data, object_hook=from_json)
            print('Reusing settings: {0!s}'.format(settings_file))

            device_id = cached_settings.get('device_id')
            # reuse auth settings
            api = Client(
                args.username, args.password,
                settings=cached_settings)

    except (ClientCookieExpiredError, ClientLoginRequiredError) as e:
        print(
            'ClientCookieExpiredError/ClientLoginRequiredError: {0!s}'.format(e))

        # Login expired
        # Do relogin but use default ua, keys and such
        api = Client(
            args.username, args.password,
            device_id=device_id,
            on_login=lambda x: onlogin_callback(x, args.settings_file_path))

    except ClientLoginError as e:
        print('ClientLoginError {0!s}'.format(e))
        exit(9)
    except ClientError as e:
        print('ClientError {0!s} (Code: {1:d}, Response: {2!s})'.format(
            e.msg, e.code, e.error_response))
        exit(9)
    except Exception as e:
        print('Unexpected Exception: {0!s}'.format(e))
        exit(99)

    # Show when login expires
    cookie_expiry = api.cookie_jar.auth_expires
    print('Cookie Expiry: {0!s}'.format(datetime.datetime.fromtimestamp(
        cookie_expiry).strftime('%Y-%m-%dT%H:%M:%SZ')))

    people_who_likes = set()
    user_id = api.authenticated_user_id
    rank_token = api.generate_uuid(seed=args.username)

    followings_data = api.user_following(user_id, rank_token)
    followings = list(map(lambda user: {
                      'username': user['username'], 'user_id': user['pk']}, followings_data['users']))

    current_user_feed = api.self_feed()
    posts = current_user_feed['items']

    for post in posts[:10]:
        people_who_liked_a_post = api.media_likers(post['id'])
        for person in people_who_liked_a_post['users']:
            people_who_likes.add(person['username'])

    followings_usernames = set(map(lambda user: user['username'], followings))
    bad_people = followings_usernames - people_who_likes

    print('There\'s %d person you follow but never liked any of your posts' %
          len(bad_people))
    
    unfollowed = 0
    for bad_person in bad_people:
        print('Username: {}'.format(bad_person))
        user_decision = input('Unfollow? [y/n]:')
        if user_decision == 'y':
            bad_person_user_id = next(
                (user for user in followings if user['username'] == bad_person), None)
            api.friendships_destroy(bad_person_user_id['user_id'])
            unfollowed += 1
        else:
            continue

    print('You unfollowed %d out of %d' % (unfollowed, len(bad_people)))
