#
# Copyright (c) 2022 Airbyte, Inc., all rights reserved.
#
import time
from abc import ABC
from collections import deque
from typing import Any, Iterable, List, Mapping, MutableMapping, Optional, Union

import pendulum
import requests
from airbyte_cdk.models import SyncMode
from airbyte_cdk.sources.streams.http import HttpStream


class PostQuery(HttpStream, ABC):
    url_base = "https://api2.branch.io/v1/"

    http_method = "POST"

    cursor_field = "timestamp"
    time_interval = {"days": 1}
    state_checkpoint_interval = 1000
    # the window attribution is used to re-fetch the last 7 days of data
    #  only if the last state day is in the range of the last 7 days
    window_attribution = {"days": 7}

    def __init__(
        self,
        config: Mapping[str, Any],
        data_source: str = None,
        aggregation: str = None,
        dimensions: List[str] = None,
        filters: dict = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.requests_per_second = deque(maxlen=5)
        self.requests_per_minute = deque(maxlen=20)
        self.requests_per_hour = deque(maxlen=150)

        self._branch_key = config["branch_key"]
        self._branch_secret = config["branch_secret"]
        self._start_date = config["start_date"]
        self._end_date = config.get("end_date")
        self._data_source = data_source
        self._aggregation = aggregation
        self._dimensions = dimensions
        self._filters = filters

    @property
    def primary_key(self) -> Optional[List[str]]:
        return [self.cursor_field] + self._dimensions

    def add_request(self):
        timestamp = time.time()
        self.requests_per_second.append(timestamp)
        self.requests_per_minute.append(timestamp)
        self.requests_per_hour.append(timestamp)

    def should_try(self):
        current_time = time.time()
        if len(self.requests_per_second) >= 5 and (current_time - self.requests_per_second[0]) < 1:
            return False
        if len(self.requests_per_minute) >= 20 and (current_time - self.requests_per_minute[0]) < 60:
            return False
        if len(self.requests_per_hour) >= 150 and (current_time - self.requests_per_hour[0]) < 3600:
            return False
        return True

    def backoff_time(self, response: requests.Response) -> Optional[float]:
        current_time = time.time()
        try:
            wait_times = [
                1 - (current_time - self.requests_per_second[0]),
                60 - (current_time - self.requests_per_minute[0]),
                3600 - (current_time - self.requests_per_hour[0]),
            ]
        except IndexError:
            return 60
        return max(wait_times, default=60)

    def get_updated_state(self, current_stream_state: MutableMapping[str, Any], latest_record: Mapping[str, Any]):
        current_stream_state = current_stream_state or {}
        current_stream_state[self.cursor_field] = pendulum.parse(latest_record[self.cursor_field]).to_date_string()
        return current_stream_state

    def next_page_token(self, response: requests.Response) -> Optional[Mapping[str, Any]]:
        if pagination := response.json().get("paging"):
            if pagination.get("next_url") is None:
                return None
            params = pagination["next_url"].split("?")[1].split("&")
            limit = None
            after = None
            for param in params:
                key, value = param.split("=")
                if key == "limit":
                    limit = int(value)
                elif key == "after":
                    after = int(value)
            return {"limit": limit, "after": after}
        return None

    def path(
        self, stream_state: Mapping[str, Any] = None, stream_slice: Mapping[str, Any] = None, next_page_token: Mapping[str, Any] = None
    ) -> str:
        return "query/analytics"

    def request_params(
        self,
        stream_state: Mapping[str, Any],
        stream_slice: Mapping[str, Any] = None,
        next_page_token: Mapping[str, Any] = None,
    ) -> MutableMapping[str, Any]:
        if next_page_token:
            return {
                "after": next_page_token.get("after"),
                "limit": next_page_token.get("limit"),
            }
        return {}

    def request_body_json(
        self,
        stream_state: Mapping[str, Any],
        stream_slice: Mapping[str, Any] = None,
        next_page_token: Mapping[str, Any] = None,
    ) -> Optional[Mapping]:
        request_data = {
            "branch_key": self._branch_key,
            "branch_secret": self._branch_secret,
            "start_date": stream_slice["start_date"],
            "end_date": stream_slice["end_date"],
            "data_source": self._data_source,
            "aggregation": self._aggregation,
            "dimensions": self._dimensions,
            "granularity": "all",
            "zero_fill": False,
            "enable_install_recalculation": False,
            "ordered_by": "name",
            "ordered": "ascending",
        }
        if self._filters:
            request_data["filters"] = self._filters
        return request_data

    def parse_response(
        self,
        response: requests.Response,
        stream_state: Mapping[str, Any],
        stream_slice: Mapping[str, Any] = None,
        next_page_token: Mapping[str, Any] = None,
    ) -> Iterable[Mapping]:
        # adding a request each time to avoid throttling
        self.add_request()

        results = response.json().get("results", [])
        for result in results:
            record = result.get("result", {})
            record["timestamp"] = result["timestamp"]
            record["data_source"] = self._data_source
            record["aggregation"] = self._aggregation
            yield record

    def stream_slices(
        self, sync_mode: SyncMode, cursor_field: List[str] = None, stream_state: Mapping[str, Any] = None
    ) -> Iterable[Optional[Mapping[str, Any]]]:
        stream_state = stream_state or {}
        if stream_state.get(self.cursor_field):
            start_date = pendulum.parse(stream_state[self.cursor_field])
            if pendulum.now().subtract(**self.window_attribution) < start_date < pendulum.now():
                start_date = pendulum.parse(stream_state[self.cursor_field]).subtract(**self.window_attribution)
        else:
            start_date = pendulum.parse(self._start_date)

        end_date = pendulum.parse(self._end_date or pendulum.now().to_date_string())

        while start_date <= end_date and start_date <= pendulum.parse(pendulum.now().to_date_string()):
            starting_at = start_date.to_date_string()
            ending_at = start_date.to_date_string()

            yield {
                "start_date": starting_at,
                "end_date": ending_at,
            }
            start_date = start_date.add(days=1)

    def get_json_schema(self):
        """
        Compose json schema based on user defined metrics.
        """
        local_json_schema = {
            "$schema": "http://json-schema.org/schema#",
            "type": "object",
            "properties": {},
        }

        fields = [self.cursor_field] + self._dimensions + [self._aggregation]
        fields = sorted(fields)

        for field in fields:
            # for each field, replace the space with underscore
            # this is happening because some of the events have spaces in their names
            local_json_schema["properties"][field.replace(" ", "_")] = {"type": ["null", "string"]}

        return local_json_schema


# Data sources:
# - eo_install
# - xx_click
# - eo_open
# - eo_commerce_event
# - eo_user_lifecycle_event

# Dimensions:
# - name
# - last_attributed_touch_data_tilde_advertising_partner_name
# - last_attributed_touch_data_tilde_keyword

# Aggregations:
# - unique_count


class Installs(PostQuery):
    def __init__(self, config: Mapping[str, Any], **kwargs):
        super().__init__(
            config=config,
            data_source="eo_install",
            aggregation="unique_count",
            dimensions=[
                "name",
                "last_attributed_touch_data_tilde_advertising_partner_name",
                "last_attributed_touch_data_tilde_keyword",
            ],
            filters={"attributed": "true"},
            **kwargs,
        )


class Clicks(PostQuery):
    def __init__(self, config: Mapping[str, Any], **kwargs):
        super().__init__(
            config=config,
            data_source="xx_click",
            aggregation="unique_count",
            dimensions=[
                "name",
                "last_attributed_touch_data_tilde_advertising_partner_name",
                "last_attributed_touch_data_tilde_keyword",
            ],
            **kwargs,
        )


class Opens(PostQuery):
    def __init__(self, config: Mapping[str, Any], **kwargs):
        super().__init__(
            config=config,
            data_source="eo_open",
            aggregation="unique_count",
            dimensions=[
                "name",
                "last_attributed_touch_data_tilde_advertising_partner_name",
                "last_attributed_touch_data_tilde_keyword",
            ],
            filters={"attributed": "true"},
            **kwargs,
        )


class CommerceEvents(PostQuery):
    def __init__(self, config: Mapping[str, Any], **kwargs):
        super().__init__(
            config=config,
            data_source="eo_commerce_event",
            aggregation="unique_count",
            dimensions=[
                "name",
                "last_attributed_touch_data_tilde_advertising_partner_name",
                "last_attributed_touch_data_tilde_keyword",
            ],
            filters={"attributed": "true"},
            **kwargs,
        )


class UserLifecycleEvent(PostQuery):
    def __init__(self, config: Mapping[str, Any], **kwargs):
        super().__init__(
            config=config,
            data_source="eo_user_lifecycle_event",
            aggregation="unique_count",
            dimensions=[
                "name",
                "last_attributed_touch_data_tilde_advertising_partner_name",
                "last_attributed_touch_data_tilde_keyword",
            ],
            filters={"attributed": "true"},
            **kwargs,
        )
