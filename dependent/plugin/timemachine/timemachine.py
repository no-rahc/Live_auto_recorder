"""
$description South Korean live-streaming platform for gaming, entertainment, and other creative content. Owned by Naver.
$url chzzk.naver.com
$type live, vod
"""

import logging
import re

from streamlink.plugin import Plugin, pluginmatcher
from streamlink.plugin.api import validate
from streamlink.stream.hls import HLSStream

log = logging.getLogger(__name__)


class ChzzkAPI:
    _CHANNELS_LIVE_DETAIL_URL = "https://api.chzzk.naver.com/service/v3/channels/{channel_id}/live-detail"
    _TIME_MACHINE_URL = "https://api.chzzk.naver.com/service/v1/live/{live_id}/playback/time-machine"

    def __init__(self, session):
        self._session = session

    def _query_api(self, url, *schemas):
        response = self._session.http.get(
            url,
            acceptable_status=(200, 404),
            schema=validate.Schema(
                validate.parse_json(),
                validate.any(
                    validate.all(
                        {"code": int, "message": str},
                        validate.transform(lambda data: ("error", data["message"])),
                    ),
                    validate.all(
                        {"code": 200, "content": dict},
                        validate.get("content"),
                        *schemas,
                        validate.transform(lambda data: ("success", data)),
                    ),
                ),
            ),
        )
        return response

    def get_live_detail(self, channel_id):
        return self._query_api(
            self._CHANNELS_LIVE_DETAIL_URL.format(channel_id=channel_id),
            {
                "status": str,
                "liveId": int,
                "liveTitle": validate.any(str, None),
                "liveCategory": validate.any(str, None),
                "adult": bool,
                "channel": validate.all(
                    {"channelName": str},
                    validate.get("channelName"),
                ),
            },
            validate.union_get("status", "liveId", "channel", "liveCategory", "liveTitle", "adult"),
        )

    def get_time_machine(self, live_id):
        return self._query_api(
            self._TIME_MACHINE_URL.format(live_id=live_id),
            {
                "playback": {
                    "media": [
                        validate.all(
                            {"mediaId": str, "protocol": str, "path": validate.url()},
                            validate.union_get("mediaId", "protocol", "path"),
                        ),
                    ],
                },
            },
            validate.get("playback", "media"),
        )


@pluginmatcher(
    name="live",
    pattern=re.compile(r"https?://chzzk\.naver\.com/live/(?P<channel_id>[^/?]+)"),
)
@pluginmatcher(
    name="video",
    pattern=re.compile(r"https?://chzzk\.naver\.com/video/(?P<video_id>[^/?]+)"),
)
class Timemachine(Plugin):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._api = ChzzkAPI(self.session)

    def _get_live(self, channel_id):
        # Step 1: Get live details
        datatype, data = self._api.get_live_detail(channel_id)
        if datatype == "error":
            print(f"[ERROR] Live detail error: {data}")
            return

        if not data:
            print("[ERROR] No live detail data available.")
            return

        status, live_id, self.author, self.category, self.title, adult = data
        if status != "OPEN":
            print("[ERROR] The stream is unavailable.")
            return

        # Step 2: Use liveId to call Time Machine API
        datatype, time_machine_data = self._api.get_time_machine(live_id)
        if datatype == "error":
            print(f"[ERROR] Time machine API error: {time_machine_data}")
            return

        print(f"[DEBUG] Time machine API response: {time_machine_data}")

        # Validate the structure of time_machine_data
        media_list = time_machine_data.get("media")
        if not media_list or not isinstance(media_list, list):
            print("[ERROR] No media data available in time machine API or invalid format.")
            return

        # Step 3: Process media list and find the best stream
        for media_item in media_list:
            print(f"[DEBUG] Processing media item: {media_item}")
            if isinstance(media_item, dict):
                # 扁粮 贸府 规侥 (dict老 版快)
                media_id = media_item.get("mediaId")
                media_protocol = media_item.get("protocol")
                media_path = media_item.get("path")
            elif isinstance(media_item, (tuple, list)) and len(media_item) >= 3:
                # Tuple 肚绰 List老 版快
                media_id, media_protocol, media_path = media_item[:3]
            else:
                print(f"[ERROR] Invalid media item structure: {media_item}")
                continue

            # Validate and return HLS stream
            if media_protocol == "HLS" and media_id == "HLS":
                print(f"[INFO] Found HLS stream: {media_path}")
                try:
                    return HLSStream.parse_variant_playlist(self.session, media_path)
                except Exception as e:
                    print(f"[WARN] Failed to parse variant playlist. Using direct stream. Error: {e}")
                    return HLSStream(self.session, media_path)


        print("[ERROR] No playable HLS stream found.")
        return



    def _get_video(self, video_id):
        print("Video support is not implemented in this plugin.")
        return

    def _get_streams(self):
        if self.matches["live"]:
            return self._get_live(self.match["channel_id"])
        elif self.matches["video"]:
            return self._get_video(self.match["video_id"])


__plugin__ = Timemachine
