# SPDX-License-Identifier: CC-BY-NC-SA-4.0

import chn_class
from helpers.htmlentityhelper import HtmlEntityHelper
from helpers.jsonhelper import JsonHelper
from mediaitem import MediaItem
from logger import Logger
from regexer import Regexer
from urihandler import UriHandler
from parserdata import ParserData
from streams.m3u8 import M3u8
from helpers.datehelper import DateHelper
from addonsettings import AddonSettings
from xbmcwrapper import XbmcWrapper
from helpers.languagehelper import LanguageHelper
# noinspection PyUnresolvedReferences
from awsidp import AwsIdp
from vault import Vault


class Channel(chn_class.Channel):
    """
    main class from which all channels inherit
    """

    def __init__(self, channel_info):
        """ Initialisation of the class.

        All class variables should be instantiated here and this method should not
        be overridden by any derived classes.

        :param ChannelInfo channel_info: The channel info object to base this channel on.

        """

        chn_class.Channel.__init__(self, channel_info)

        # setup the main parsing data
        if self.channelCode == "vijfbe":
            self.noImage = "vijfimage.png"
            self.mainListUri = "https://www.vijf.be/programmas"
            self.baseUrl = "https://www.vijf.be"

        elif self.channelCode == "zesbe":
            self.noImage = "zesimage.png"
            self.mainListUri = "https://www.zestv.be/programmas"
            self.baseUrl = "https://www.zestv.be"

        else:
            self.noImage = "vierimage.png"
            self.mainListUri = "https://www.vier.be/programmas"
            self.baseUrl = "https://www.vier.be"

        episode_regex = '<a class="program-overview__link" href="(?<url>[^"]+)">(?<title>[^<]+)</a>'
        episode_regex = Regexer.from_expresso(episode_regex)
        self._add_data_parser(self.mainListUri, match_type=ParserData.MatchExact,
                              parser=episode_regex,
                              creator=self.create_episode_item)

        video_regex = r'<a(?:[^>]+data-background-image="(?<thumburl>[^"]+)")?[^>]+href="' \
                      r'(?<url>/video/[^"]+)"[^>]*>(?:\s+<div[^>]+>\s+<div [^>]+' \
                      r'data-background-image="(?<thumburl2>[^"]+)")?[\w\W]{0,1000}?' \
                      r'<h3[^>]*>(?:<span>)?(?<title>[^<]+)(?:</span>)?</h3>(?:\s+' \
                      r'(?:<div[^>]*>\s+)?<div[^>]*>[^<]+</div>\s+<div[^>]+data-timestamp=' \
                      r'"(?<timestamp>\d+)")?'
        video_regex = Regexer.from_expresso(video_regex)
        self._add_data_parser("*", match_type=ParserData.MatchExact,
                              name="Normal video items",
                              parser=video_regex,
                              creator=self.create_video_item)

        page_regex = r'<button class="button button--default js-load-more-button"\W+data-url=' \
                     r'"(?<url>[^"]+)"\W+data-page="(?<title>\d+)"'
        page_regex = Regexer.from_expresso(page_regex)
        self._add_data_parser("*", match_type=ParserData.MatchExact,
                              parser=page_regex,
                              creator=self.create_page_item)

        self._add_data_parser("/api/program/fixed/", name="API paging",
                              match_type=ParserData.MatchContains,
                              preprocessor=self.extract_page_data,
                              parser=video_regex,
                              creator=self.create_video_item)

        # Generic updater with login
        self._add_data_parser("*", updater=self.update_video_item)

        # ==========================================================================================
        # Channel specific stuff
        self.__idToken = None

        # ==========================================================================================
        # Test cases:
        # Documentaire: pages (has http://www.canvas.be/tag/.... url)
        # Not-Geo locked: Kroost

        # ====================================== Actual channel setup STOPS here ===================
        return

    def log_on(self):
        """ Logs on to a website, using an url.

        First checks if the channel requires log on. If so and it's not already
        logged on, it should handle the log on. That part should be implemented
        by the specific channel.

        More arguments can be passed on, but must be handled by custom code.

        After a successful log on the self.loggedOn property is set to True and
        True is returned.

        :return: indication if the login was successful.
        :rtype: bool

        """

        if self.__idToken:
            return True

        # check if there is a refresh token
        # refresh token: viervijfzes_refresh_token
        refresh_token = AddonSettings.get_setting("viervijfzes_refresh_token")
        client = AwsIdp("eu-west-1_dViSsKM5Y", "6s1h851s8uplco5h6mqh1jac8m",
                        proxy=self.proxy, logger=Logger.instance())
        if refresh_token:
            id_token = client.renew_token(refresh_token)
            if id_token:
                self.__idToken = id_token
                return True
            else:
                Logger.info("Extending token for VierVijfZes failed.")

        # username: viervijfzes_username
        username = AddonSettings.get_setting("viervijfzes_username")
        # password: viervijfzes_password
        v = Vault()
        password = v.get_setting("viervijfzes_password")
        if not username or not password:
            XbmcWrapper.show_dialog(
                title=None,
                lines=LanguageHelper.get_localized_string(LanguageHelper.MissingCredentials),
            )
            return False

        id_token, refresh_token = client.authenticate(username, password)
        if not id_token or not refresh_token:
            Logger.error("Error getting a new token. Wrong password?")
            return False

        self.__idToken = id_token
        AddonSettings.set_setting("viervijfzes_refresh_token", refresh_token)
        return True

    def create_episode_item(self, result_set):
        """ Creates a new MediaItem for an episode.

        This method creates a new MediaItem from the Regular Expression or Json
        results <result_set>. The method should be implemented by derived classes
        and are specific to the channel.

        :param list[str]|dict[str,str] result_set: The result_set of the self.episodeItemRegex

        :return: A new MediaItem of type 'folder'.
        :rtype: MediaItem|None

        """

        item = chn_class.Channel.create_episode_item(self, result_set)
        if item is None:
            return item

        # All of vier.be video's seem GEO locked.
        item.isGeoLocked = True
        item.thumb = item.thumb or self.noImage
        return item

    def create_page_item(self, result_set):
        """ Creates a MediaItem of type 'page' using the result_set from the regex.

        This method creates a new MediaItem from the Regular Expression or Json
        results <result_set>. The method should be implemented by derived classes
        and are specific to the channel.

        :param list[str]|dict[str,str] result_set: The result_set of the self.episodeItemRegex

        :return: A new MediaItem of type 'page'.
        :rtype: MediaItem|None

        """

        result_set["url"] = "{0}/{1}".format(result_set["url"], result_set["title"])
        result_set["title"] = str(int(result_set["title"]) + 1)

        item = self.create_folder_item(result_set)
        item.type = "page"
        return item

    def extract_page_data(self, data):
        """ Performs pre-process actions for data processing.

        Accepts an data from the process_folder_list method, BEFORE the items are
        processed. Allows setting of parameters (like title etc) for the channel.
        Inside this method the <data> could be changed and additional items can
        be created.

        The return values should always be instantiated in at least ("", []).

        :param str data: The retrieve data that was loaded for the current item and URL.

        :return: A tuple of the data and a list of MediaItems that were generated.
        :rtype: tuple[str|JsonHelper,list[MediaItem]]

        """

        items = []
        json = JsonHelper(data)
        data = json.get_value("data")
        Logger.trace(data)

        if json.get_value("loadMore", fallback=False):
            url, page = self.parentItem.url.rsplit("/", 1)
            url = "{0}/{1}".format(url, int(page) + 1)
            page_item = MediaItem("{0}".format(int(page) + 2), url)
            page_item.type = "page"
            items.append(page_item)
        return data, items

    def create_video_item(self, result_set):
        """ Creates a MediaItem of type 'video' using the result_set from the regex.

        This method creates a new MediaItem from the Regular Expression or Json
        results <result_set>. The method should be implemented by derived classes
        and are specific to the channel.

        If the item is completely processed an no further data needs to be fetched
        the self.complete property should be set to True. If not set to True, the
        self.update_video_item method is called if the item is focussed or selected
        for playback.

        :param list[str]|dict[str,str] result_set: The result_set of the self.episodeItemRegex

        :return: A new MediaItem of type 'video' or 'audio' (despite the method's name).
        :rtype: MediaItem|None

        """

        item = chn_class.Channel.create_video_item(self, result_set)

        # All of vier.be video's seem GEO locked.
        item.isGeoLocked = True

        # Set the correct url
        # videoId = resultSet["videoid"]
        # item.url = "https://api.viervijfzes.be/content/%s" % (videoId, )
        time_stamp = result_set.get("timestamp")
        if time_stamp:
            date_time = DateHelper.get_date_from_posix(int(result_set["timestamp"]))
            item.set_date(date_time.year, date_time.month, date_time.day, date_time.hour,
                          date_time.minute,
                          date_time.second)

        if not item.thumb and "thumburl2" in result_set and result_set["thumburl2"]:
            item.thumb = result_set["thumburl2"]

        if item.thumb and item.thumb != self.noImage:
            item.thumb = HtmlEntityHelper.strip_amp(item.thumb)
        return item

    def update_video_item(self, item):
        """ Updates an existing MediaItem with more data.

        Used to update none complete MediaItems (self.complete = False). This
        could include opening the item's URL to fetch more data and then process that
        data or retrieve it's real media-URL.

        The method should at least:
        * cache the thumbnail to disk (use self.noImage if no thumb is available).
        * set at least one MediaItemPart with a single MediaStream.
        * set self.complete = True.

        if the returned item does not have a MediaItemPart then the self.complete flag
        will automatically be set back to False.

        :param MediaItem item: the original MediaItem that needs updating.

        :return: The original item with more data added to it's properties.
        :rtype: MediaItem

        """

        Logger.debug('Starting update_video_item for %s (%s)', item.name, self.channelName)

        # https://api.viervijfzes.be/content/c58996a6-9e3d-4195-9ecf-9931194c00bf
        # videoId = item.url.split("/")[-1]
        # url = "%s/video/v3/embed/%s" % (self.baseUrl, videoId,)
        url = item.url
        data = UriHandler.open(url, proxy=self.proxy)
        return self.__update_video(item, data)

    def __update_video(self, item, data):
        regex = 'data-file="([^"]+)'
        m3u8_url = Regexer.do_regex(regex, data)[-1]

        if ".m3u8" not in m3u8_url:
            Logger.info("Not a direct M3u8 file. Need to log in")
            url = "https://api.viervijfzes.be/content/%s" % (m3u8_url, )

            # We need to log in
            if not self.loggedOn:
                self.log_on()

            # add authorization header
            authentication_header = {
                "authorization": self.__idToken,
                "content-type": "application/json"
            }
            data = UriHandler.open(url, proxy=self.proxy, additional_headers=authentication_header)
            json_data = JsonHelper(data)
            m3u8_url = json_data.get_value("video", "S")

        # Geo Locked?
        if "geo" in m3u8_url.lower():
            # set it for the error statistics
            item.isGeoLocked = True

        part = item.create_new_empty_media_part()
        for s, b in M3u8.get_streams_from_m3u8(m3u8_url, self.proxy):
            if int(b) < 200:
                Logger.info("Skipping stream of quality '%s' kbps", b)
                continue

            item.complete = True
            part.append_media_stream(s, b)

        item.complete = True
        return item
