# encoding: utf-8
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from __future__ import unicode_literals

import requests
import traceback
import unittest
from collections import OrderedDict
from pulsebot.pulse import PulseListener
import logging


logger = logging.getLogger(__name__)


class PulseHgPushes(PulseListener):
    def __init__(self, config):
        super(PulseHgPushes, self).__init__(
            config.pulse_user,
            config.pulse_password,
            "exchange/hgpushes/v1",
            "#",
            config.pulse_applabel if config.pulse_applabel else None,
        )

    def __iter__(self):
        for message in super(PulseHgPushes, self).__iter__():
            for push in self.get_pushes_info(message):
                yield push

    @staticmethod
    def get_pushes_info(pulse_message):
        # Sanity checks
        logger.info("get_pushes_info")
        try:
            payload = pulse_message.get("payload", {})
            pushes = payload.get("pushlog_pushes")
            if not pushes:
                return
        except Exception:
            logger.exception("Failure on retrieving payload data from pulse_message")
            return

        for push in pushes:
            push_url = push.get("push_full_json_url")
            if not push_url:
                continue
            logger.info(f"get_push_info_from: {push_url}")
            try:
                for data in PulseHgPushes.get_push_info_from(push_url):
                    yield data
            except Exception:
                logger.exception(f"Failure on {push_url}")
                for line in traceback.format_exc().splitlines():
                    logger.debug(line)
                logger.debug("Message data was: %r", pulse_message)
                continue

    @staticmethod
    def get_push_info_from(push_url):
        repo = push_url[: push_url.rindex("/")]
        r = requests.get(push_url)
        if r.status_code != requests.codes.ok:
            # If we were not successful, try again once.
            r = requests.get(push_url)
        if r.status_code != requests.codes.ok:
            logger.exception(f"Failure getting {push_url} {r.status_code}")
            return

        data = r.json(object_pairs_hook=OrderedDict)

        for id, d in data.get("pushes", {}).items():
            id = int(id)
            push_data = {
                "pushlog": "%s/pushloghtml?startID=%d&endID=%d" % (repo, id - 1, id),
                "user": d.get("user"),
                "changesets": [],
            }

            for cs in d.get("changesets", ()):
                short_node = cs["node"][:12]
                revlink = "%s/rev/%s" % (repo, short_node)

                desc = [line.strip() for line in cs["desc"].splitlines()]
                data = {
                    "revlink": revlink,
                    "desc": desc[0].strip(),
                    "author": cs["author"].split(" <")[0].strip(),
                }
                if len(cs["parents"]) > 1:
                    data["is_merge"] = True
                for line in desc:
                    if line.startswith("Source-Repo:"):
                        data["source-repo"] = line.split(" ", 1)[1]
                push_data["changesets"].append(data)

            yield push_data


class TestPushesInfo(unittest.TestCase):
    def test_pushes_info(self):
        # Not ideal: this relies on actual live data.
        results = [
            {
                "pushlog": "https://hg.mozilla.org/integration/mozilla-inbound/"
                "pushloghtml?startID=5&endID=6",
                "user": "eakhgari@mozilla.com",
                "changesets": [
                    {
                        "author": "Rafael Ávila de Espíndola",
                        "revlink": "https://hg.mozilla.org/integration/mozilla-inbound/"
                        "rev/685f5ae6e7de",
                        "desc": "Bug 657653. Check for libstdc++ versions in "
                        "stdc++compat.cpp; r=ted,glandium",
                    }
                ],
            },
            {
                "pushlog": "https://hg.mozilla.org/integration/mozilla-inbound/"
                "pushloghtml?startID=6&endID=7",
                "user": "rocallahan@mozilla.com",
                "changesets": [
                    {
                        "author": "Robert O'Callahan",
                        "revlink": "https://hg.mozilla.org/integration/mozilla-inbound/"
                        "rev/63c8f645cc1c",
                        "desc": "Bug 661471. Part 6.1: Expose "
                        "cairo_win32_get_system_text_quality. r=jfkthame",
                    },
                    {
                        "author": "Robert O'Callahan",
                        "revlink": "https://hg.mozilla.org/integration/mozilla-inbound/"
                        "rev/3eb99af46b93",
                        "desc": "Bug 661471. Part 6.2: Handle dynamic changes to "
                        "Cleartype enabled/disabled. r=jfkthame",
                    },
                    {
                        "author": "Jonathan Kew",
                        "revlink": "https://hg.mozilla.org/integration/mozilla-inbound/"
                        "rev/1ccc676a3a2c",
                        "desc": "Bug 661471. Part 6.3: Ensure that force_gdi_classic "
                        "doesn't make us use ClearType when ClearType is "
                        "disabled. r=roc",
                    },
                    {
                        "author": "Jonathan Kew",
                        "revlink": "https://hg.mozilla.org/integration/mozilla-inbound/"
                        "rev/5607cca3f7bf",
                        "desc": "Bug 661471. Part 7: Let gfxDWriteFonts know whether "
                        "we are honouring 'GDI classic' overrides. r=roc",
                    },
                ],
            },
        ]

        message = {
            "payload": {
                "repo_url": "https://hg.mozilla.org/integration/mozilla-inbound",
                "pushlog_pushes": [
                    {
                        "push_full_json_url": "https://hg.mozilla.org/integration/mozilla-inbound/"
                        "json-pushes?version=2&full=1&startID=6&endID=7"
                    },
                ],
            }
        }

        pushes = list(PulseHgPushes.get_pushes_info(message))

        self.maxDiff = None
        self.assertEqual(pushes, [results[1]])

        message = {
            "payload": {
                "repo_url": "https://hg.mozilla.org/integration/mozilla-inbound",
                "pushlog_pushes": [
                    {
                        "push_full_json_url": "https://hg.mozilla.org/integration/mozilla-inbound/"
                        "json-pushes?version=2&full=1&startID=5&endID=6"
                    },
                    {
                        "push_full_json_url": "https://hg.mozilla.org/integration/mozilla-inbound/"
                        "json-pushes?version=2&full=1&startID=6&endID=7"
                    },
                ],
            }
        }

        pushes = list(PulseHgPushes.get_pushes_info(message))

        self.assertEqual(pushes, results)

        message = {
            "payload": {
                "repo_url": "https://hg.mozilla.org/integration/mozilla-inbound",
                "pushlog_pushes": [
                    {
                        "push_full_json_url": "https://hg.mozilla.org/integration/mozilla-inbound/"
                        "json-pushes?version=2&full=1&startID=5&endID=7"
                    },
                ],
            }
        }

        pushes = list(PulseHgPushes.get_pushes_info(message))

        self.maxDiff = None
        self.assertEqual(pushes, results)

        message = {
            "payload": {
                "repo_url": "https://hg.mozilla.org/integration/autoland",
                "pushlog_pushes": [
                    {
                        "push_full_json_url": "https://hg.mozilla.org/integration/autoland/"
                        "json-pushes?version=2&full=1&startID=36889&endID=36890"
                    },
                ],
            }
        }

        pushes = list(PulseHgPushes.get_pushes_info(message))

        self.assertEqual(
            [p["source-repo"] for p in pushes[0]["changesets"] if "source-repo" in p],
            ["https://github.com/servo/servo"] * 8274,
        )

        pushes[0]["changesets"] = [
            p for p in pushes[0]["changesets"] if "source-repo" not in p
        ]

        self.maxDiff = None
        servo_results = [
            {
                "changesets": [
                    {
                        "author": "Gregory Szorc",
                        "revlink": "https://hg.mozilla.org/integration/autoland/"
                        "rev/be030db91f00",
                        "desc": "Bug 1322769 - Free the oxidized lizzard, vendor "
                        "Servo",
                        "is_merge": True,
                    }
                ],
                "pushlog": "https://hg.mozilla.org/integration/autoland/"
                "pushloghtml?startID=36889&endID=36890",
                "user": "gszorc@mozilla.com",
            }
        ]
        self.assertEqual(pushes, servo_results)
