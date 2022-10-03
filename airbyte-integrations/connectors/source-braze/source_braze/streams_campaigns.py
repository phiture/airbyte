#
# Copyright (c) 2022 Airbyte, Inc., all rights reserved.
#
import json
from typing import Any, Iterable, List, Mapping, MutableMapping, Optional

import pendulum
import requests
from airbyte_cdk.models import SyncMode
from airbyte_cdk.sources.streams import IncrementalMixin
from airbyte_cdk.sources.streams.http import HttpSubStream
from source_braze.streams import BrazeStream


class CampaignsList(BrazeStream):
    use_cache = True
    primary_key = "campaign_id"
    _current_page = 0

    def path(
        self, stream_state: Mapping[str, Any] = None, stream_slice: Mapping[str, Any] = None, next_page_token: Mapping[str, Any] = None
    ) -> str:
        return "campaigns/list"

    def next_page_token(self, response: requests.Response) -> Optional[Mapping[str, Any]]:
        if response.status_code == 200:
            # if the response is a success and items are 100, we need to get the next page
            # otherwise, we're done
            if "campaigns" in response.json() and len(response.json()["campaigns"]) == 100:
                if self._current_page < self._pages:
                    self._current_page += 1
                    return {"page": self._current_page}
            else:
                return None

        return None

    def parse_response(
        self,
        response: requests.Response,
        stream_state: Mapping[str, Any],
        stream_slice: Mapping[str, Any] = None,
        next_page_token: Mapping[str, Any] = None,
    ) -> Iterable[Mapping]:
        # The response is a simple JSON whose schema matches our stream's schema exactly,
        # so we just return a list containing the response
        campaigns = response.json()["campaigns"]
        for campaign in campaigns:
            campaign[self.primary_key] = campaign["id"]
            yield campaign

    def request_params(
        self, stream_state: Mapping[str, Any], stream_slice: Mapping[str, any] = None, next_page_token: Mapping[str, Any] = None
    ) -> MutableMapping[str, Any]:
        self.logger.info(f"Fetching {self.name} page: {self._current_page} of {self._pages}")
        return {
            "page": next_page_token["page"] if next_page_token else self._current_page,
        }


class CampaignsDetails(HttpSubStream, BrazeStream):
    primary_key = "campaign_id"

    def __init__(self, **kwargs):
        super().__init__(CampaignsList(**kwargs), **kwargs)

    def path(
        self, stream_state: Mapping[str, Any] = None, stream_slice: Mapping[str, Any] = None, next_page_token: Mapping[str, Any] = None
    ) -> str:
        return "campaigns/details"

    def parse_response(
        self,
        response: requests.Response,
        stream_state: Mapping[str, Any],
        stream_slice: Mapping[str, Any] = None,
        next_page_token: Mapping[str, Any] = None,
    ) -> Iterable[Mapping]:
        # The response is a simple JSON whose schema matches our stream's schema exactly,
        # so we just return a list containing the response
        data = response.json()

        # adding the campaign id to the campaign details object
        data[self.primary_key] = stream_slice["parent"][self.parent.primary_key]

        # convert the messages object to a list
        messages = []
        for message_id, message in data.get("messages", {}).items():
            message["message_id"] = message_id
            # convert headers object to string
            if "headers" in message:
                message["headers"] = json.dumps(message["headers"])
            messages.append(message)
        data["messages"] = messages

        # add order to conversion behaviors
        order = 1
        for conversion_behavior in data.get("conversion_behaviors", []):
            conversion_behavior["order"] = order
            order += 1

        yield data

    def request_params(
        self, stream_state: Mapping[str, Any], stream_slice: Mapping[str, any] = None, next_page_token: Mapping[str, Any] = None
    ) -> MutableMapping[str, Any]:
        self.logger.info(f'Fetching {self.name} campaign_id: {stream_slice["parent"][self.parent.primary_key]}')
        return {
            "campaign_id": stream_slice["parent"][self.parent.primary_key],
        }


class CampaignsDataSeries(HttpSubStream, IncrementalMixin, BrazeStream):
    primary_key = ["campaign_id", "time"]
    cursor_field = "time"
    time_interval = {"days": 30}
    # the window attribution is used to re-fetch the last 30 days of data
    #  only if the last state day is in the range of the last 30 days
    window_attribution = {"days": 30}

    def __init__(self, **kwargs):
        super().__init__(CampaignsDetails(**kwargs), **kwargs)
        self._state = {}

    @property
    def state(self) -> MutableMapping[str, Any]:
        return self._state

    @state.setter
    def state(self, value: MutableMapping[str, Any]):
        self._state.update(value)

    def current_state(self, campaign_id, default=None):
        default = default or self.state.get(self.cursor_field)
        return self.state.get(campaign_id, {}).get(self.cursor_field) or default

    def path(
        self, stream_state: Mapping[str, Any] = None, stream_slice: Mapping[str, Any] = None, next_page_token: Mapping[str, Any] = None
    ) -> str:
        return "campaigns/data_series"

    def parse_response(
        self,
        response: requests.Response,
        stream_state: Mapping[str, Any],
        stream_slice: Mapping[str, Any] = None,
        next_page_token: Mapping[str, Any] = None,
    ) -> Iterable[Mapping]:
        # The response is a simple JSON whose schema matches our stream's schema exactly,
        # so we just return a list containing the response
        data_series = response.json()["data"]

        # iterate over the data series and add the campaign id to the data series object
        for data_series_item in data_series:
            # adding the campaign id to the campaign data series object
            data_series_item[self.parent.primary_key] = stream_slice["parent"][self.parent.primary_key]

            # convert the messages object to a list
            new_messages = []
            for message_key, messages in data_series_item.get("messages", {}).items():
                for message in messages:
                    message["type"] = message_key
                    new_messages.append(message)
            data_series_item["messages"] = new_messages

            yield data_series_item

    def stream_slices(self, sync_mode: SyncMode, stream_state: Mapping[str, Any] = None, **kwargs) -> Iterable[Optional[Mapping[str, Any]]]:
        for parent_slice in super().stream_slices(sync_mode=sync_mode):
            if parent_slice["parent"]["first_sent"] is None and parent_slice["parent"]["last_sent"] is None:
                continue

            stream_state = stream_state or {}
            campaign_id = parent_slice["parent"][self.parent.primary_key]

            if stream_state.get(campaign_id):
                start_date = pendulum.parse(stream_state[campaign_id].get(self.cursor_field))
                if pendulum.now().subtract(**self.window_attribution) < start_date < pendulum.now():
                    start_date = pendulum.parse(parent_slice["parent"]["last_sent"]).subtract(**self.window_attribution)
            else:
                start_date = pendulum.parse(parent_slice["parent"]["first_sent"])

            end_date = pendulum.parse(parent_slice["parent"]["last_sent"])

            # if the campaign start date is before the created date,
            #  use created_at as start_date
            created_date = pendulum.parse(parent_slice["parent"]["created_at"])
            if start_date < created_date:
                start_date = created_date

            if start_date.to_date_string() == end_date.to_date_string():
                end_date = end_date.add(days=1)

            while start_date <= end_date:
                starting_at = start_date
                ending_at = start_date.add(**self.time_interval)

                # if ending day is after NOW(), set ending_at to NOW()
                if ending_at >= pendulum.now():
                    ending_at = pendulum.now()

                self.logger.info(
                    f"Fetching {self.name} campaign_id: {campaign_id} ; time range: {starting_at.to_date_string()} - {ending_at.to_date_string()}"
                )

                yield {
                    "parent": parent_slice["parent"],
                    "starting_at": starting_at.to_date_string(),
                    "ending_at": ending_at.to_date_string(),
                }
                start_date = start_date.add(**self.time_interval)

    def read_records(
        self, sync_mode: SyncMode, cursor_field: List[str] = None, stream_slice: MutableMapping[str, Any] = None, **kwargs
    ) -> Iterable[Mapping[str, Any]]:
        campaign_id = stream_slice and stream_slice["parent"]["campaign_id"]
        for record in super().read_records(sync_mode=sync_mode, stream_slice=stream_slice):
            current_state = self.current_state(campaign_id)
            if current_state:
                date_in_current_stream = pendulum.parse(current_state)
                date_in_latest_record = pendulum.parse(record[self.cursor_field])
                cursor_value = (max(date_in_current_stream, date_in_latest_record)).to_date_string()
                self.state = {campaign_id: {self.cursor_field: cursor_value}}
                yield record
                continue
            self.state = {campaign_id: {self.cursor_field: record[self.cursor_field]}}
            yield record

    def request_params(self, stream_slice: Mapping[str, Any], **kwargs) -> MutableMapping[str, Any]:
        return {
            "campaign_id": stream_slice["parent"][self.parent.primary_key],
            "length": self.time_interval["days"],
            "ending_at": pendulum.parse(stream_slice["ending_at"]).to_date_string(),
        }
