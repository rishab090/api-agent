import requests
from typing import List, Dict, Optional, Union
from langchain_core.tools import Tool, StructuredTool
from pydantic import BaseModel

class APITableConfig:
    def __init__(self, 
                 name: str, 
                 description: str,
                 pk: Union[str, List[str]], 
                 relationships: List[Dict] = None,
                 name_field: Optional[str] = None):
        
        self.name = name
        self.description = description
        self.pk = pk if isinstance(pk, list) else [pk]
        self.relationships = relationships or []
        self.name_field = name_field 

class APILookup:
    def __init__(self, 
                 config: APITableConfig,
                 url: str, 
                 json_key: str = "data", 
                 headers: Optional[Dict] = None, 
                 payload: Optional[Dict] = None, 
                 method: str = "POST"):
        
        self.config = config
        self.url = url
        self.json_key = json_key
        self.headers = headers or {"Content-Type": "application/json"}
        self.payload = payload or {}
        self.method = method.upper()
        self._cache = None
        self.safe_name = self.config.name.lower().replace(" ", "_")

    def _fetch_data(self) -> List[Dict]:
        if self._cache is not None: return self._cache

        try:
            if self.method == "POST":
                r = requests.post(self.url, json=self.payload, headers=self.headers, verify=False, timeout=10)
            else:
                r = requests.get(self.url, headers=self.headers, params=self.payload, verify=False, timeout=10)
            
            if r.status_code != 200: return []
            raw_list = r.json().get(self.json_key, []) or []
            
            cleaned_list = []
            for item in raw_list:
                if isinstance(item, dict):
                    entry = {"details": item}
                    cleaned_list.append(entry)
            
            self._cache = cleaned_list
            return cleaned_list
        except Exception:
            return []

    def _get_schema_details(self, input_str: str = ""):
        c = self.config
        info = f"TABLE: {self.safe_name}\nDESCRIPTION: {c.description}\n"
        info += f"PRIMARY KEY: {', '.join(c.pk)}\n"
        
        if c.name_field:
            info += f"NAME COLUMN: '{c.name_field}'\n"
        
        if c.relationships:
            info += "RELATIONSHIPS (JOINS) - STRICTLY FOLLOW THESE:\n"
            for rel in c.relationships:
                my_cols = ", ".join(rel['my_cols'])
                target_cols = ", ".join(rel['target_cols'])
                info += f"  - JOIN {self.safe_name}.{my_cols} = {rel['target_table']}.{target_cols}\n"
        
        data = self._fetch_data()
        if data:
            requested_attrs = self.payload.get("attributes", [])
            
            mandatory_cols = set(self.config.pk)
            for rel in self.config.relationships:
                mandatory_cols.update(rel['my_cols'])

            if requested_attrs:
                display_cols = list(set(requested_attrs) | mandatory_cols)
            else:
                display_cols = list(data[0]['details'].keys())

            info += f"ALL COLUMNS: {', '.join(display_cols)}\n"
            
            examples = data[:3]
            info += "\nEXAMPLE ROWS:\n"
            for i, row in enumerate(examples, 1):
                filtered_row = {k: row['details'].get(k, "N/A") for k in display_cols if k in row['details']}
                info += f"Row {i}: {filtered_row}\n"
            
        return info

    def _get_schema_details_no_args(self) -> str:
        return self._get_schema_details("")

    def get_schema_tool(self) -> StructuredTool:
        class NoInputModel(BaseModel):
            pass

        return StructuredTool.from_function(
            func=self._get_schema_details_no_args,
            name=f"describe_{self.safe_name}",
            description=f"Returns the database schema and sample rows for the '{self.config.name}' table. Use this to understand the columns before querying.",
            args_schema=NoInputModel
        )