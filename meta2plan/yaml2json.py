import yaml
import json

yaml_path = 'solution_metadata_v6_modified.yaml'
json_path = 'solution_metadata_v6_modified.json'

with open(yaml_path, encoding='UTF-8') as f: 
    yaml_data = yaml.load(f, Loader=yaml.FullLoader)
    json_data = json.dumps(yaml_data)

with open(json_path, 'w') as f: 
    json.dump(json_data, f)
    
    