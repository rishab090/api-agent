import os
from langchain_openai import AzureChatOpenAI
from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits import SQLDatabaseToolkit
from langchain_community.agent_toolkits.sql.base import create_sql_agent
from langchain.agents.agent_types import AgentType


os.environ["AZURE_OPENAI_API_KEY"] = os.environ.get("AZURE_OPENAI_API_KEY", "Azure_API_Key")
os.environ["AZURE_OPENAI_ENDPOINT"] = os.environ.get("AZURE_OPENAI_ENDPOINT", "https://openai-ragbot.openai.azure.com/")


db_uri = "sqlite:///test.db" 

db = SQLDatabase.from_uri(db_uri)

llm = AzureChatOpenAI(
    azure_deployment="gpt-4.1-mini",  
    openai_api_version="2024-12-01-preview", 
    temperature=0,             
    verbose=True
)

toolkit = SQLDatabaseToolkit(db=db, llm=llm)

agent_executor = create_sql_agent(
    llm=llm,
    toolkit=toolkit,
    verbose=True,
    agent_type="openai-tools",
    handle_parsing_errors=True
)


def run_sql_agent(query: str):
    try:
        system_rules = (
            "Given the following user question, corresponding SQL query, and SQL result, answer the user question. You are only allowed to perform Select operations. No Update, Alter, Delete Commands allowed. Explicitly ask user to contact BI team for such requests.\n"
            "Question: "
        )
        print(f" SQL Agent working on: {query}:")
        response = agent_executor.invoke(system_rules + query)
        return response["output"]
    except Exception as e:
        return f"SQL Agent Error: {str(e)}"

if __name__ == "__main__":

    result = run_sql_agent("can you update the name of product as Athena_U where product id is 1.")
    print(result)