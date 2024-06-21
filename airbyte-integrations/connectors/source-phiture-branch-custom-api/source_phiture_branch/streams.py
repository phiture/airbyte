import json
import time
from abc import ABC
from collections import deque
from typing import Any, Iterable, List, Mapping, MutableMapping, Optional

import pendulum
import requests
from airbyte_cdk.models import SyncMode
from airbyte_cdk.sources.streams.http import HttpStream


class PostQuery(HttpStream, ABC):
    url_base = 'https://api2.branch.io/v2/logs?app_id=1098525421886001912'

    http_method = "POST"

    cursor_field = "timestamp"
    time_interval = {"days": 1}
    state_checkpoint_interval = 1000
    window_attribution = {"days": 7}

    def __init__(
            self,
            config: Mapping[str, Any],
            report_type: str = None,
            fields: List[str] = None,
            filter: List[str] = None,
            timezone: str = None,
            response_format: str = None,
            limit: int = None,
            **kwargs,
    ):
        super().__init__(**kwargs)
        self.requests_per_second = deque(maxlen=1)
        self.requests_per_minute = deque(maxlen=5)
        self.requests_per_hour = deque(maxlen=10)

        self._start_date = config["start_date"]
        self._end_date = config.get("end_date")
        self._report_type = report_type
        self._fields = fields
        self._filter = config.get("filter")
        self._timezone = timezone
        self._response_format = response_format
        self._limit = limit
        self._access_token = config["access_token"]

    @property
    def primary_key(self) -> Optional[List[str]]:
        return [self.cursor_field] + self._fields

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

    # def get_updated_state(self, current_stream_state: MutableMapping[str, Any], latest_record: Mapping[str, Any]):
    #     current_stream_state = current_stream_state or {}
    #     current_stream_state[self.cursor_field] = pendulum.parse(latest_record[self.cursor_field]).to_date_string()
    #     return current_stream_state

    def get_updated_state(self, current_stream_state: MutableMapping[str, Any], latest_record: Mapping[str, Any]):
        current_stream_state = current_stream_state or {}

        # Ensure the latest_record contains the cursor field (timestamp)
        if self.cursor_field not in latest_record:
            # Log a warning or handle the error as needed
            print(f"Warning: {self.cursor_field} not found in the latest record. Skipping state update.")
            return current_stream_state

        try:
            # Parse the timestamp and update the state
            timestamp_value = pendulum.parse(latest_record[self.cursor_field]).to_date_string()
            current_stream_state[self.cursor_field] = timestamp_value
        except Exception as e:
            # Handle any parsing errors
            print(f"Error parsing timestamp in the latest record: {e}")

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
        return ""

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

    def request_headers(
            self,
            stream_state: Mapping[str, Any],
            stream_slice: Mapping[str, Any] = None,
            next_page_token: Mapping[str, Any] = None
    ) -> Mapping[str, Any]:
        headers = {
            'Access-Token': f'{self._access_token}',
            'accept': 'application/json',
            'content-type': 'application/json',
        }
        if self._access_token:
            print("Access token included in the request headers!")
        else:
            print("Warning: Access token is missing from the request headers!")
        print("Request headers:", headers)
        return headers

    def request_body_json(
            self,
            stream_state: Mapping[str, Any],
            stream_slice: Mapping[str, Any] = None,
            next_page_token: Mapping[str, Any] = None,
    ) -> Optional[Mapping]:
        request_data = {
            "report_type": self._report_type,
            "fields": self._fields,
            "limit": self._limit,
            "timezone": self._timezone,
            "filter": self._filter,
            "response_format": self._response_format,
            "start_date": stream_slice["start_date"],
            "end_date": stream_slice["end_date"],
        }
        json_data = json.dumps(request_data)
        print("Request body JSON data:", json_data)
        return json.loads(json_data)

    def parse_response(
            self,
            response: requests.Response,
            stream_state: Mapping[str, Any],
            stream_slice: Mapping[str, Any] = None,
            next_page_token: Mapping[str, Any] = None,
    ) -> Iterable[Mapping]:
        # adding a request each time to avoid throttling
        self.add_request()
        try:
            initial_response = response.json()
            print("Initial response:", initial_response)
            export_job_status_url = initial_response.get("export_job_status_url")
        except json.JSONDecodeError as e:
            # # Handle malformed JSON
            # print(f"Error parsing response: {e}")
            # try:
            #     export_job_status_url = initial_response["export_job_status_url"]
            #     print("Export job status URL found in the response", export_job_status_url)
            # except Exception as e:
            #     print(f"Error parsing response: {e}")
            #     return
            return  # Early return to avoid further processing

        if not export_job_status_url:
            raise Exception("Export job status URL not found in the response")

        download_url = self.check_export_status(export_job_status_url)
        data = self.download_data(download_url)
        # print("Downloaded data:", data.text)
        # try:
        #     print("Downloaded data as JSON:", data.json())
        # except json.JSONDecodeError as e:
        #     # Handle malformed JSON
        #     print(f"Error parsing Downloaded data: {e}")
        #
        # # Process the downloaded data
        # try:
        #     if data.json() and data.json().get("name") is not None:
        #         for result in data.json():
        #             print("Result:", result)
        #             record = result.get("result", {})
        #             record["timestamp"] = result["timestamp"]
        #             record["report_type"] = self._report_type
        #             yield record
        #     print("Data processed successfully!", record)
        # except json.JSONDecodeError as e:
        #     # Handle malformed JSON
        #     print(f"Error parsing downloaded data: {e}")

        try:
            datas = data.json()
            print("Downloaded data as JSON:", datas)
            return datas
        except json.JSONDecodeError:
            print("Error parsing downloaded data as JSON:", data.text)
            # Handle case where response contains multiple JSON objects
            datas = []
            for line in data.text.splitlines():
                line = line.strip()
                if line:
                    try:
                        datas.append(json.loads(line))
                    except json.JSONDecodeError as e:
                        print(f"Skipping line due to JSONDecodeError: {e}")
            print("Downloaded data as JSON:", datas)
            return datas

    def check_export_status(self, export_job_status_url: str):
        headers = self.request_headers({}, {})
        while True:
            response = requests.get(export_job_status_url, headers=headers)
            status_response = response.json()

            # Print status for debugging
            print("Export job status response:", status_response)

            if status_response.get('status') == 'complete':
                return status_response.get('response_url')
            elif status_response.get('status') == 'failed':
                raise Exception("Export job failed")
            else:
                time.sleep(5)  # Wait for 5 seconds before checking again

    def download_data(self, download_url: str):
        headers = self.request_headers({}, {})
        response = requests.get(download_url, headers=headers)
        response.raise_for_status()  # Raise an exception if the request was unsuccessful

        # Assuming the response content is JSON
        data = response
        return data

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

        end_date = pendulum.parse(self._end_date or pendulum.now().to_iso8601_string())

        while start_date < end_date and start_date < pendulum.now():
            starting_at = start_date.to_iso8601_string()
            ending_at = start_date.add(days=1).to_iso8601_string()

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

        fields = [self.cursor_field] + self._fields
        fields = sorted(fields)

        for field in fields:
            # for each field, replace the space with underscore
            # this is happening because some of the events have spaces in their names
            data_type = "string"
            local_json_schema["properties"][field.replace(" ", "_")] = {"type": ["null", data_type]}
        print("JSON schema:", local_json_schema)
        return local_json_schema


class Clicks(PostQuery):
    def __init__(self, config: Mapping[str, Any], **kwargs):
        super().__init__(
            config=config,
            report_type="eo_click",
            timezone=config["timezone"],
            response_format=config["response_format"],
            fields=config["fields"],
            limit=config["limit"],
            **kwargs,
        )


class CommerceEvents(PostQuery):
    def __init__(self, config: Mapping[str, Any], **kwargs):
        super().__init__(
            config=config,
            report_type="eo_commerce_event",
            timezone=config["timezone"],
            response_format=config["response_format"],
            fields=config["fields"],
            limit=config["limit"],
            **kwargs,
        )


class Impressions(PostQuery):
    def __init__(self, config: Mapping[str, Any], **kwargs):
        super().__init__(
            config=config,
            report_type="eo_impression",
            timezone=config["timezone"],
            response_format=config["response_format"],
            fields=config["fields"],
            limit=config["limit"],
            **kwargs,
        )


class Installs(PostQuery):
    def __init__(self, config: Mapping[str, Any], **kwargs):
        super().__init__(
            config=config,
            report_type="eo_install",
            timezone=config["timezone"],
            response_format=config["response_format"],
            fields=config["fields"],
            limit=config["limit"],
            **kwargs,
        )


class Opens(PostQuery):
    def __init__(self, config: Mapping[str, Any], **kwargs):
        super().__init__(
            config=config,
            report_type="eo_open",
            timezone=config["timezone"],
            response_format=config["response_format"],
            fields=config["fields"],
            limit=config["limit"],
            **kwargs,
        )


class Reinstalls(PostQuery):
    def __init__(self, config: Mapping[str, Any], **kwargs):
        super().__init__(
            config=config,
            report_type="eo_reinstall",
            timezone=config["timezone"],
            response_format=config["response_format"],
            fields=config["fields"],
            limit=config["limit"],
            **kwargs,
        )


class UserLifecycleEvent(PostQuery):
    def __init__(self, config: Mapping[str, Any], **kwargs):
        super().__init__(
            config=config,
            report_type="eo_user_lifecycle_event",
            timezone=config["timezone"],
            response_format=config["response_format"],
            fields=config["fields"],
            limit=config["limit"],
            **kwargs,
        )

class CustomEvents(PostQuery):
    def __init__(self, config: Mapping[str, Any], **kwargs):
        super().__init__(
            config=config,
            report_type="eo_custom_event",
            timezone=config["timezone"],
            response_format=config["response_format"],
            fields=config["fields"],
            limit=config["limit"],
            **kwargs,
        )
