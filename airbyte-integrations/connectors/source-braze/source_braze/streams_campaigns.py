#
# Copyright (c) 2022 Airbyte, Inc., all rights reserved.
#


from typing import Any, Iterable, Mapping, Optional, MutableMapping

import pendulum
import requests
from airbyte_cdk.models import SyncMode
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
            if 'campaigns' in response.json() and len(response.json()['campaigns']) == 100:
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
        self.logger.info(
            f'Fetching {self.name} page: {self._current_page} of {self._pages}')
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
            messages.append(message)
        data["messages"] = messages

        order = 1
        for conversion_behavior in data.get("conversion_behaviors", []):
            conversion_behavior["order"] = order
            order += 1

        yield data

    def request_params(
            self, stream_state: Mapping[str, Any], stream_slice: Mapping[str, any] = None, next_page_token: Mapping[str, Any] = None
    ) -> MutableMapping[str, Any]:
        self.logger.info(
            f'Fetching {self.name} campaign_id: {stream_slice["parent"][self.parent.primary_key]}')
        return {
            "campaign_id": stream_slice["parent"][self.parent.primary_key],
        }


class CampaignsDataSeries(HttpSubStream, BrazeStream):
    primary_key = "campaign_id"
    date_template = "%Y-%m-%d"
    time_interval = {"days": 100}

    def __init__(self, **kwargs):
        super().__init__(CampaignsDetails(**kwargs), **kwargs)
        self._start_date = pendulum.parse(kwargs["config"]["start_date"])

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
            data_series_item[self.primary_key] = stream_slice["parent"][self.parent.primary_key]

            # convert the messages object to a list
            new_messages = []
            for message_key, messages in data_series_item.get("messages", {}).items():
                for message in messages:
                    message["type"] = message_key
                    new_messages.append(message)
            data_series_item["messages"] = new_messages

            yield data_series_item

    def stream_slices(self, stream_state: Mapping[str, Any] = None, **kwargs) -> Iterable[Optional[Mapping[str, Any]]]:
        for parent_slice in super().stream_slices(sync_mode=SyncMode.full_refresh):
            # get the start and end date from the config
            # start_date = self._start_date
            # end_date = pendulum.now()

            # FIXME: uncomment this if you want a use first_entry and last_entry as start and end date
            if parent_slice["parent"]["first_sent"] is not None \
                    and parent_slice["parent"]["last_sent"] is not None:
                start_date = pendulum.parse(parent_slice["parent"]["first_sent"])
                end_date = pendulum.parse(parent_slice["parent"]["last_sent"])
                if start_date.strftime(self.date_template) == end_date.strftime(self.date_template):
                    end_date = end_date.add(days=1)
            else:
                continue

            while start_date <= end_date:
                starting_at = start_date
                ending_at = start_date.add(**self.time_interval)

                # if ending day is after NOW(), set ending_at to NOW()
                if ending_at >= pendulum.now():
                    ending_at = pendulum.now()

                self.logger.info(
                    f"Fetching {self.name} campaign_id: {parent_slice['parent'][self.parent.primary_key]} ; time range: {starting_at.strftime(self.date_template)} - {ending_at.strftime(self.date_template)}")

                yield {
                    "parent": parent_slice["parent"],
                    "starting_at": starting_at.strftime(self.date_template),
                    "ending_at": ending_at.strftime(self.date_template),
                }
                start_date = start_date.add(**self.time_interval)

    def request_params(self, stream_slice: Mapping[str, Any], **kwargs) -> MutableMapping[str, Any]:
        return {
            "campaign_id": stream_slice["parent"][self.parent.primary_key],
            "length": self.time_interval["days"],
            "ending_at": pendulum.parse(stream_slice["ending_at"]).strftime(self.date_template),
        }
