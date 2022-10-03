mkdir sample_files
echo '{"start_date": "2022-04-01", "app_token": "<app_token_key>", "user_token": "<user_token>"}'  > secrets/config.json
echo '{"start_date": "1022-04-01", "app_token": "<app_token_key>", "user_token": "<user_token>"}'  > secrets/invalid_config.json
python main.py check --config secrets/config.json
python main.py check --config secrets/invalid_config.json