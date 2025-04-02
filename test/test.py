import json
from config import MPLSConfig
json_file_path = r"/demo/test.json"


with open(json_file_path, 'r') as file:
    json_data = json.load(file)


config = MPLSConfig(json_data)

print(config.generate_config("PE1"))

# print(config.generate_all_configs())