import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.types import Text
from langchain_core.tools import Tool
from typing import List
from api_class import APILookup 
from sqlalchemy.pool import StaticPool

class GlobalDataManager:
    def __init__(self, apis: List[APILookup]):
        self.apis = apis
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool
        )
        self.is_loaded = False

    def refresh_data(self):
        print("Loading all data into Mem DB:")
        
        for api in self.apis:
            data = api._fetch_data() 
            if not data: continue
            
            raw_rows = [item['details'] for item in data]
            df = pd.DataFrame(raw_rows)
            
            str_cols = df.select_dtypes(include=['object']).columns
            dtype_mapping = {col: Text(collation='NOCASE') for col in str_cols}

            df.to_sql(api.safe_name, self.engine, index=False, if_exists='replace', dtype=dtype_mapping)
            print(f"  Loaded table: {api.safe_name} ({len(df)} rows)")
            
        self.is_loaded = True
        return "Data load complete. Tables are ready for joining."

    def run_global_sql(self, query: str):
        if not self.is_loaded:
            self.refresh_data()
            
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(query))
                keys = result.keys()
                rows = [dict(zip(keys, row)) for row in result.fetchall()]
                
                if len(rows) > 50:
                    truncated = rows[:50]
                    truncated.append({"System Note": f"Results truncated. {len(rows)} total rows found. Please refine your query (e.g., add WHERE or LIMIT)."})
                    return truncated
                return rows
        except Exception as e:
            return f"SQL Error: {str(e)}"

    def get_master_sql_tool(self) -> Tool:
        table_names = [api.safe_name for api in self.apis]
        desc = f"Executes SQL queries on the Central Database. Available tables: {', '.join(table_names)}. You can perform JOINS between these tables."
        
        return Tool(
            name="execute_global_sql",
            func=self.run_global_sql,
            description=desc
        )