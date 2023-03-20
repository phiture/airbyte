#
# Copyright (c) 2022 Airbyte, Inc., all rights reserved.
#
from abc import ABC
from typing import Any, Iterable, Mapping, MutableMapping, Optional

import pendulum
import requests
from airbyte_cdk.models import SyncMode
from airbyte_cdk.sources.streams.http import HttpStream


class GetReports(HttpStream, ABC):
    url_base = "https://api.mobileaction.co"
    http_method = "POST"

    primary_key = None
    cursor_field = "day"
    time_interval = {"days": 1}
    state_checkpoint_interval = 1000
    # the window attribution is used to re-fetch the last 7 days of data
    #  only if the last state day is in the range of the last 7 days
    window_attribution = {"days": 7}

    def __init__(self, config: Mapping[str, Any], report_type: str, report_level: str, **kwargs):
        super().__init__(**kwargs)
        self._state = {}

        self._api_token = config["api_token"]
        self._start_date = config["start_date"]
        self._end_date = config.get("end_date")
        self._org_id = config["org_id"]
        self._re_attr_type = config.get("re_attr_type")
        self._lat_on_factor = config.get("lat_on_factor")
        self._goals_ids = config.get("goals_ids")
        if self._goals_ids:
            self._goals_ids = self._goals_ids.split(",")
            # remove empty strings
            self._goals_ids = list(filter(None, self._goals_ids))
            # remove leading and trailing spaces
            self._goals_ids = [int(goal_id.strip()) for goal_id in self._goals_ids]

        self._report_type = report_type
        self._report_level = report_level

        if self._report_level is None and self._report_type is None:
            exit("report_type and report_level must be set")

    def next_page_token(self, response: requests.Response) -> Optional[Mapping[str, Any]]:
        response_obj = response.json()
        params = response_obj["data"][0]["pagination"]

        items_per_page = params["limit"]
        total_items = params["totalRowCount"]
        offset = params["offset"]

        if offset > total_items:
            return None
        else:
            return {"page": offset // items_per_page + 1}

    def backoff_time(self, response: requests.Response) -> Optional[float]:
        if int(response.headers.get("X-Ratelimit-Remaining", -1)) == 0:
            rate_limit_replenish_rate = float(response.headers.get("X-Ratelimit-Replenish-Rate", -1))
            if rate_limit_replenish_rate == -1:
                return 1.0  # Default backoff time if rate limit headers are not available

            tokens_needed = int(response.headers.get("X-Ratelimit-Requested-Tokens", 1))
            time_to_replenish = tokens_needed / rate_limit_replenish_rate
            backoff_time = time_to_replenish * 1.5  # Add a safety margin of 50%

            return backoff_time

        return None

    def path(
            self, stream_state: Mapping[str, Any] = None, stream_slice: Mapping[str, Any] = None, next_page_token: Mapping[str, Any] = None
    ) -> str:
        return "searchads/reports"

    def request_params(
            self,
            stream_state: Mapping[str, Any],
            stream_slice: Mapping[str, Any] = None,
            next_page_token: Mapping[str, Any] = None,
    ) -> MutableMapping[str, Any]:
        # the page is set to 0 if there is no next_page_token
        next_page = next_page_token["page"] if next_page_token else 0
        self.logger.info(
            f"Fetching {self.name} ;"
            f' time range: {stream_slice["start_date"]} - {stream_slice["end_date"]} ;'
            f' goalId: {stream_slice.get("goal_id")} ;'
            f" page: {next_page}"
        )
        return {
            "token": self._api_token,
            "page": next_page,
        }

    def request_body_json(
            self,
            stream_state: Mapping[str, Any],
            stream_slice: Mapping[str, Any] = None,
            next_page_token: Mapping[str, Any] = None,
    ) -> Optional[Mapping]:
        request_body = {
            "reportType": self._report_type,
            "reportLevel": self._report_level,
            "orgIds": [self._org_id],
            "startDate": stream_slice["start_date"],
            "endDate": stream_slice["end_date"],
            "reAttrType": self._re_attr_type,
            "latOnFactor": self._lat_on_factor,
        }
        if stream_slice.get("goal_id"):
            request_body["goalId"] = stream_slice["goal_id"]
        return request_body

    def parse_response(
            self,
            response: requests.Response,
            stream_state: Mapping[str, Any],
            stream_slice: Mapping[str, Any] = None,
            next_page_token: Mapping[str, Any] = None,
    ) -> Iterable[Mapping]:
        """
        Parse the response from the API request and extract the relevant data.

        Args:
            response (requests.Response): Response object from the API request.
            stream_state (Mapping[str, Any]): Current state of the stream.
            stream_slice (Mapping[str, Any], optional): Data to be streamed in the current iteration. Defaults to None.
            next_page_token (Mapping[str, Any], optional): Token to retrieve next page of data (if applicable). Defaults to None.

        Yields:
            Iterable[Mapping]: A dictionary containing the relevant data.
        """
        data = response.json()  # Convert response to JSON format
        for row in data["data"][0]["tableData"]:
            row["day"] = stream_slice["start_date"]  # Add start date to row data
            row["goalId"] = stream_slice.get("goal_id")  # Add goal id to row data (if applicable)
            yield row  # Yield the processed data row

    def stream_slices(self, sync_mode: SyncMode, stream_state: Mapping[str, Any] = None, **kwargs) -> Iterable[Optional[Mapping[str, Any]]]:
        """
        Yields a sequence of dictionaries, each representing a time window for fetching data from the source.
        Each dictionary includes a start and end date for the time window and, if applicable, a goal ID.

        Args:
            sync_mode (SyncMode): The synchronization mode to use.
            stream_state (Mapping[str, Any], optional): A mapping of stream state information. Defaults to None.
            **kwargs: Additional keyword arguments.

        Yields:
            Iterable[Optional[Mapping[str, Any]]]: A sequence of dictionaries representing time windows for data fetching.
        """
        # Initialize stream state to an empty dictionary if not provided.
        stream_state = stream_state or {}

        # If the stream state includes the cursor field, use it to determine the starting date for the time window.
        if stream_state.get(self.cursor_field):
            start_date = pendulum.parse(stream_state[self.cursor_field])

            # If the starting date falls within the attribution window, adjust it to the beginning of the window.
            if pendulum.now().subtract(**self.window_attribution) < start_date < pendulum.now():
                start_date = pendulum.parse(stream_state[self.cursor_field]).subtract(**self.window_attribution)
        else:
            # Otherwise, use the start date provided during initialization.
            start_date = pendulum.parse(self._start_date)

        # Determine the end date for the time window.
        end_date = pendulum.parse(self._end_date or pendulum.now().to_date_string())

        # Yield dictionaries representing time windows until the end date or current date is reached.
        while start_date <= end_date and start_date < pendulum.parse(pendulum.now().to_date_string()):
            starting_at = start_date
            ending_at = start_date

            if self._goals_ids:
                # If goal IDs are specified, yield dictionaries for each goal ID and time window.
                for goal_id in self._goals_ids:
                    yield {
                        "start_date": starting_at.to_date_string(),
                        "end_date": ending_at.to_date_string(),
                        "goal_id": goal_id,
                    }
            else:
                # Otherwise, yield a single dictionary for the time window.
                yield {
                    "start_date": starting_at.to_date_string(),
                    "end_date": ending_at.to_date_string(),
                }

            # Increment the start date by the time interval between windows.
            start_date = start_date.add(**self.time_interval)

    def get_updated_state(self, current_stream_state: MutableMapping[str, Any], latest_record: Mapping[str, Any]):
        current_stream_state = current_stream_state or {}
        current_stream_state[self.cursor_field] = pendulum.parse(latest_record[self.cursor_field]).to_date_string()
        return current_stream_state


class GetReportsReportAdGroup(GetReports):
    primary_key = [
        "day",
        "goalId",
        "orgId",
        "orgName",
        "country",
        "currency",
        "appId",
        "appName",
        "campaignId",
        "campaignName",
        "adGroupId",
        "adGroupName",
        "gender",
        "deviceClass",
        "customerType",
    ]

    def __init__(self, config: Mapping[str, Any], **kwargs):
        super().__init__(config, report_type="REPORT", report_level="AD_GROUP", **kwargs)
