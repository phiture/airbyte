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
from source_phiture_braze.streams import BrazeStream


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
            "include_archived": self.include_archived,
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


class CampaignsDataSeries(HttpSubStream, BrazeStream):
    time_interval = {"days": 100}
    primary_key = ["campaign_id", "time"]

    def __init__(self, **kwargs):
        super().__init__(CampaignsDetails(**kwargs), **kwargs)

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
            if parent_slice["parent"]["created_at"] is None or parent_slice["parent"]["last_sent"] is None:
                continue

            start_date = pendulum.parse(parent_slice["parent"]["created_at"])
            end_date = pendulum.parse(parent_slice["parent"]["last_sent"])

            if start_date.to_date_string() == end_date.to_date_string():
                end_date = end_date.add(days=1)

            while start_date <= end_date:
                starting_at = start_date.start_of("day")
                ending_at = min(starting_at.add(days=self.time_interval["days"]).end_of("day"), end_date.end_of("day"))

                # if ending day is after NOW(), set ending_at to NOW()
                if ending_at >= pendulum.now().utcnow():
                    ending_at = pendulum.now().utcnow()

                self.logger.info(
                    f"Fetching {self.name} campaign_id: {parent_slice['parent'][self.parent.primary_key]} ; time range: {start_date.to_iso8601_string()} - {ending_at.to_iso8601_string()}"
                )

                yield {
                    "parent": parent_slice["parent"],
                    "starting_at": starting_at.to_iso8601_string(),
                    "ending_at": ending_at.to_iso8601_string(),
                }
                start_date = start_date.add(days=self.time_interval["days"])

    def request_params(self, stream_slice: Mapping[str, Any], **kwargs) -> MutableMapping[str, Any]:
        return {
            "campaign_id": stream_slice["parent"][self.parent.primary_key],
            "length": self.time_interval["days"],
            "ending_at": stream_slice["ending_at"],
        }
