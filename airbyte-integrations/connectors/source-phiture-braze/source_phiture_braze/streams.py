#
# Copyright (c) 2022 Airbyte, Inc., all rights reserved.
#
import time
from abc import ABC
from typing import Any, Iterable, Mapping, Optional, Union

import requests
from airbyte_cdk.sources.streams.http import HttpStream


class BrazeStream(HttpStream, ABC):
    _url_base = None
    _pages = 300

    def __init__(self, config: Mapping[str, Any], **kwargs):
        super().__init__(**kwargs)
        self.url_base = config["instance_url"]
        self.include_archived = config["include_archived"]

    @property
    def url_base(self) -> str:
        return self._url_base

    @url_base.setter
    def url_base(self, value):
        if value.endswith("/"):
            value = value[:-1]
        if not value.startswith("https://"):
            value = "https://" + value
        self._url_base = value

    def parse_response(
        self,
        response: requests.Response,
        stream_state: Mapping[str, Any],
        stream_slice: Mapping[str, Any] = None,
        next_page_token: Mapping[str, Any] = None,
    ) -> Iterable[Mapping]:
        # The response is a simple JSON whose schema matches our stream's schema exactly,
        # so we just return a list containing the response
        return [response.json()]

    def backoff_time(self, response: requests.Response) -> Union[None, int, float]:
        """
        This method is called if we run into the rate limit.
        Braze limits request to 250.000 requests per hour per endpoint.

        https://www.braze.com/docs/api/api_limits/#monitoring-your-rate-limits

        # `X-RateLimit-Reset` header which contains time when this hour
        # will be finished and limits will be reset so
        # we again could have 250.000 requests per hour per endpoint.
        """
        if response.status_code == requests.codes.SERVER_ERROR:
            return None

        retry_after = int(response.headers.get("Retry-After", 0))
        if retry_after:
            return retry_after

        reset_time = response.headers.get("X-RateLimit-Reset")
        backoff_time = float(reset_time) - time.time() if reset_time else 60

        return max(backoff_time, 60)  # This is a guarantee that no negative value will be returned.

    def next_page_token(self, response: requests.Response) -> Optional[Mapping[str, Any]]:
        return None
