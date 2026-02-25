import os
from langchain_openai import AzureChatOpenAI
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_core.output_parsers import CommaSeparatedListOutputParser
from api_class import APILookup, APITableConfig
from sql_memdb import GlobalDataManager
from mem0 import Memory
import json

os.environ["AZURE_OPENAI_API_KEY"] = os.environ.get("AZURE_OPENAI_API_KEY", "Azure_API_Key")
os.environ["AZURE_OPENAI_ENDPOINT"] = os.environ.get("AZURE_OPENAI_ENDPOINT", "https://openai-ragbot.openai.azure.com/")


CONFIG_FILE = "/app/data/config.json"

def load_api_configs():
    if not os.path.exists(CONFIG_FILE):
        return [], []
    
    with open(CONFIG_FILE, 'r') as f:
        config_data = json.load(f)

    configs = []
    apis = []

    for item in config_data:
        table_config = APITableConfig(
            name=item["name"],
            pk=item["pk"],
            name_field=item.get("name_field"),
            description=item["description"],
            relationships=item.get("relationships", [])
        )
        configs.append(table_config)

        api_lookup = APILookup(
            config=table_config,
            url=item["api_url"],
            json_key=item.get("json_key", "data"),
            payload=item.get("payload", {})
        )
        apis.append(api_lookup)
    
    return configs, apis

all_configs, all_apis = load_api_configs()


llm = AzureChatOpenAI(
    azure_deployment="gpt-4.1-mini",  
    openai_api_version="2024-12-01-preview", 
    temperature=0,             
    verbose=True
)

db_manager = GlobalDataManager(all_apis)

mem0_config = {
    "llm": {
        "provider": "azure_openai",
        "config": {
            "model": "gpt-4.1-mini",
            "azure_kwargs": {
                "api_key": os.environ["AZURE_OPENAI_API_KEY"],
                "azure_deployment": "gpt-4.1-mini",
                "azure_endpoint": os.environ["AZURE_OPENAI_ENDPOINT"],
                "api_version": "2024-12-01-preview",
            }
        }
    },
    "embedder": {
        "provider": "azure_openai",
        "config": {
            "model": "text-embedding-3-small",
            "azure_kwargs": {
                "api_key": os.environ["AZURE_OPENAI_API_KEY"],
                "azure_deployment": "text-embedding-3-small", 
                "azure_endpoint": os.environ["AZURE_OPENAI_ENDPOINT"],
                "api_version": "2024-12-01-preview",
            }
        }
    },
    "vector_store": {
        "provider": "chroma",
        "config": {
            "collection_name": "api_agent_memories",
            "path": "/app/data/mem0_chroma",
        }
    }
}

memory = Memory.from_config(mem0_config)

def get_session_context(session_id, window_size=5):
    try:
        results = memory.get_all(user_id=session_id)
        
        if isinstance(results, dict):
            raw_list = results.get("results", [])
        else:
            raw_list = results
            
        all_texts = []
        for item in raw_list:
            if isinstance(item, dict):
                all_texts.append(item.get('memory', ''))
            else:
                all_texts.append(str(item))

        if not all_texts:
            return "", []

        if len(all_texts) > window_size:
            older_texts = all_texts[:-window_size]
            recent_texts = all_texts[-window_size:] 
        else:
            older_texts = []
            recent_texts = all_texts

        conversation_summary = "No previous context."
        if older_texts:
            print(f"Summarizing {len(older_texts)} older messages:")
            text_block = "\n".join(older_texts)
            summary_prompt = (
                f"Summarize the following previous conversation history concisely. "
                f"Focus on the entities discussed, specific constraints applied, and the user's goal.\n\n"
                f"HISTORY:\n{text_block}"
            )
            summary_res = llm.invoke(summary_prompt)
            conversation_summary = summary_res.content

        recent_objs = []
        for text in recent_texts:
            if not isinstance(text, str):
                text = str(text)
            if "User:" in text and "Assistant:" in text:
                parts = text.split("Assistant:")
                u = parts[0].replace("User:", "").strip()
                a = parts[1].strip()
                recent_objs.append(HumanMessage(content=u))
                recent_objs.append(AIMessage(content=a))
            else:
                recent_objs.append(HumanMessage(content=text))
                
        return conversation_summary, recent_objs

    except Exception as e:
        print(f"Context Manager Error: {e}")
        return "Error loading context.", []

def select_relevant_tables(user_query, configs):
    table_menu = "\n".join([f"- {c.name}: {c.description}" for c in configs])
    router_prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a Database Router. Select relevant tables from the list. Return ONLY comma-separated names. IF NO TABLE IS RELEVANT (e.g., query is about general knowledge, manuals, technical specs not in DB), RETURN 'None'. If the query is a simple greeting or a conversational follow-up about the chat history (e.g., 'hi', 'what did I ask', 'repeat that'), RETURN 'General'."),
        ("human", "Available Tables:\n{menu}\n\nQuery: {query}")
    ])
    chain = router_prompt | llm | CommaSeparatedListOutputParser() # LCEL (LangChain Expression Language)
    return chain.invoke({"menu": table_menu, "query": user_query})

def convert_history_to_messages(history_list):
    messages = []
    for item in history_list:
        role = item.get("role", "user")
        content = item.get("content", "")
        if role == "user":
            messages.append(HumanMessage(content=content))
        elif role in ["ai", "assistant"]:
            messages.append(AIMessage(content=content))
    return messages

def run_agent(user_query, session_id="default", history=[], language="Default English"):
    print(f" User Query: {user_query} (Session: {session_id}, Language: {language})")
    
    try:
        memories = memory.search(user_query, user_id=session_id)
        semantic_facts = "\n".join([m['memory'] for m in memories]) if memories else "No relevant facts found."
    except:
        semantic_facts = "Memory Unavailable"

    if history:
        print(f"Using provided history ({len(history)} messages)")
        recent_chat_history = convert_history_to_messages(history)
        past_summary = "Refer to the chat history for context."
    else:
        past_summary, recent_chat_history = get_session_context(session_id, window_size=5)

    try:
        relevant_names = select_relevant_tables(user_query, all_configs)
        print(f" Selected Tables: {relevant_names}")

        if not relevant_names or (len(relevant_names) == 1 and "none" in relevant_names[0].lower()):
            print(" No relevant tables found (Query is likely for RAG/General).")
            return "No relevant data found in the database. This query might be better suited for the Manuals/RAG."
            
        if len(relevant_names) == 1 and "general" in relevant_names[0].lower():
            print(" Detected General Query. Proceeding without specific tables.")
            relevant_names = []
            
    except Exception as e:
        print(f"Routing Error: {e}")
        return "Error in routing."
    
    api_map = {api.config.name: api for api in all_apis}
    selected_tools = [db_manager.get_master_sql_tool()]
    
    for name in relevant_names:
        clean_name = name.strip()
        if clean_name in api_map:
            selected_tools.append(api_map[clean_name].get_schema_tool())

    prompt = ChatPromptTemplate.from_messages([
        ("system", 
         "You are a SQL Data Agent. Respond to welcome messages with a welcome message. "
         "1. Schema Tools: Use 'describe_<table_name>' tools (e.g. 'describe_equipment') to get table schemas. "
         "   **CRITICAL RULE**: NEVER call the exact same 'describe_...' tool more than ONCE. Once you see the schema, you MUST formulate a SQL query. "
         "2. Query Execution: Use the 'execute_global_sql' tool to run your SQL queries against the retrieved schemas (supports JOINs). "
         "3. Always answer based strictly on the data retrieved from 'execute_global_sql'. "
         "4. Assume the person asking has no SQL knowledge (they are a business user). "
         "5. DO NOT provide an answer without running SQL queries, except for general chat. "
         "6. Use the exact relationships/keys provided in the 'describe_...' tool outputs. "
         "7. **ISOLATION RULE**: IGNORE any information tagged as [RAG Analysis] or [Web Search] in the conversation history. ONLY use the SQL Database. "
         "8. If the user asks for specs/manuals/textual info NOT in the DB, return: 'I can only provide data from the database. Please check the Manuals Assistant.' "
         "9. **CONTEXT TAGS**: '[Context: Entity: X, Category: Y]' are VALUES to search for in your SQL WHERE clauses. "
         "   - Map 'Entity:' to 'Name' or 'Equipment' columns. "
         "   - Map 'Category:' to 'Category' columns. "
         "   - Do NOT assume columns are named 'Entity' or 'Category' without checking the schema."
         f"\n 10. **LANGUAGE RULE**: You MUST provide your final response in {language}, using conversational/daily language. DO NOT use overly formal language."
         "\n\n--- CONTEXT ---"
         "\nOLDER CONVERSATION SUMMARY: {past_summary}"
         "\nSPECIFIC RELEVANT FACTS: {semantic_facts}"
         "\n(Note: Ignore 'semantic_facts' if they come from RAG/Web sources)"
        ),
        ("placeholder", "{chat_history}"), 
        ("human", "{input}"),
        ("placeholder", "{agent_scratchpad}"),
    ])

    agent = create_tool_calling_agent(llm, selected_tools, prompt)
    agent_executor = AgentExecutor(agent=agent, tools=selected_tools, verbose=True)
    
    response = agent_executor.invoke({
        "input": user_query, 
        "past_summary": past_summary,
        "semantic_facts": semantic_facts,
        "chat_history": recent_chat_history
    })
    
    result_text = response['output']
    
    sql_log = ""
    for step in response.get("intermediate_steps", []):
        tool_name = step[0].tool
        if tool_name == "execute_global_sql":
            query = step[0].tool_input
            res = step[1]
            sql_log += f"\n[SQL EXECUTED]: {query}\n[RESULT]: {str(res)[:500]}..." 

    try:
        memory_content = f"User: {user_query}\nAssistant: {result_text}"
        if sql_log:
            memory_content += f"\nDETAILS:{sql_log}"
            
        memory.add(memory_content, user_id=session_id, metadata={"role": "interaction"}, infer=False)
    except Exception as e:
        print(f" Memory Update Error: {e}")

    return {
        "response": result_text,
        "sql_log": sql_log if sql_log else None
    }

def reload_agent_config():
    global all_configs, all_apis, db_manager
    print("Reloading API configurations:")
    all_configs, all_apis = load_api_configs()
    db_manager = GlobalDataManager(all_apis)
    print("API configurations reloaded.")