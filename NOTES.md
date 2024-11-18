Hacking with langchain seems to involve some pretty complex APIs.
Lots of tutorials go out of date quickly.
Eg this amazing Tavily demo:
https://docs.tavily.com/docs/integrations/langchain#how-to-use-tavily-api-with-langchain

... has multiple deprecation warnings.
Two are just fixing imports.
I wanted to update the `initialize_agent` call, but couldn't understand how to
do so from the docs.

Reading this article helped me understand what agents are:
https://medium.com/@prajwal_/introduction-to-langchain-agents-e692a4a19cd1

But still, I didn't know how to replace `AgentType.STRUCTURED_CHAT_ZERO_SHOT_REACT_DESCRIPTION`, and wasn't finding anything about "zero shot" in the new APIs. And what did it even mean?

I wish I had done this earlier: ask the AI!
In this case, I typed this question into a Cursor chat:

```
Can you describe what Agents are in the langchain ecosystem ?  ANd what does "zero shot" mean?
```

I got this response:

```md

Here's an explanation of Agents in LangChain and the concept of "zero-shot":

# Agents in LangChain

Agents are high-level abstractions that combine:

- LLMs (Language Models) - The "brain" that makes decisions
- Tools - Functions that the agent can use to interact with external systems or perform specific tasks
- Memory - Optional component to maintain context across interactions
- Action Planning - The ability to decide what actions to take

Think of an Agent as an AI assistant that can:

- Understand what needs to be done
- Choose appropriate tools to accomplish the task
- Execute those tools in the right order
- Interpret results and decide on next steps

Example use cases:
```

```python
# Simple agent with a search tool
agent = create_openai_functions_agent(
    llm=ChatOpenAI(),
    tools=[DuckDuckGoSearchTool()],
    prompt=prompt
)

# Agent that can both search and calculate
agent = create_openai_functions_agent(
    llm=ChatOpenAI(),
    tools=[DuckDuckGoSearchTool(), Calculator()],
    prompt=prompt
)
```

```md

# "Zero-Shot" Explained
"Zero-shot" refers to the agent's ability to use tools without any previous training examples. It means:

1. The agent can figure out which tool to use just from:
  - The tool's name
  - The tool's description
  - The current context/question
2. No previous examples ("shots") are needed

For example:

```

```py
# Zero-shot agent with multiple tools
tools = [
    Tool(
        name="Search",
        description="useful for searching the internet",
        func=search.run
    ),
    Tool(
        name="Calculator",
        description="useful for doing math calculations",
        func=calculator.run
    )
]

# The agent can figure out when to use each tool without training
# If user asks "what's 2+2", it knows to use Calculator
# If user asks "who won the 2024 Super Bowl", it knows to use Search

```

```md
This is in contrast to "few-shot" learning where you provide examples of how to use the tools, or "fine-tuning" where you train the model on many examples.
The "zero-shot" capability comes from the LLM's pre-trained understanding of language and context, allowing it to make reasonable decisions about tool usage without specific training for each tool.
```


Ok we want langchain.agents.structured_chat.base.StructuredChatAgent

and we're here:

```ipdb
---> 74         agent_kwargs = agent_kwargs or {}
     75         agent_obj = agent_cls.from_llm_and_tools(
     76             llm, tools, callback_manager=callback_manager, **agent_kwargs
     77         )
```

with this context:

```
ipdb> pp llm
ChatOpenAI(client=<openai.resources.chat.completions.Completions object at 0x107a41430>, async_client=<openai.resources.chat.completions.AsyncCompletions object at 0x107a42b40>, root_client=<openai.OpenAI object at 0x1071e4fe0>, root_async_client=<openai.AsyncOpenAI object at 0x107a41460>, model_name='gpt-4', model_kwargs={}, openai_api_key=SecretStr('**********'))
ipdb> pp tools
[TavilySearchResults(api_wrapper=TavilySearchAPIWrapper(tavily_api_key=SecretStr('**********')))]
ipdb> pp callback_manager
None
```


And the class gets instantiated and prompt created like so:

```
    109     @classmethod
    110     def from_llm_and_tools(
    111         cls,
    112         llm: BaseLanguageModel,
    113         tools: Sequence[BaseTool],
    114         callback_manager: Optional[BaseCallbackManager] = None,
    115         output_parser: Optional[AgentOutputParser] = None,
    116         prefix: str = PREFIX,
    117         suffix: str = SUFFIX,
    118         human_message_template: str = HUMAN_MESSAGE_TEMPLATE,
    119         format_instructions: str = FORMAT_INSTRUCTIONS,
    120         input_variables: Optional[List[str]] = None,
    121         memory_prompts: Optional[List[BasePromptTemplate]] = None,
    122         **kwargs: Any,
    123     ) -> Agent:
    124         """Construct an agent from an LLM and tools."""
--> 125         cls._validate_tools(tools)
    126         prompt = cls.create_prompt(
    127             tools,
    128             prefix=prefix,
    129             suffix=suffix,
    130             human_message_template=human_message_template,
    131             format_instructions=format_instructions,
    132             input_variables=input_variables,
    133             memory_prompts=memory_prompts,
    134         )
    135         llm_chain = LLMChain(
    136             llm=llm,
    137             prompt=prompt,
    138             callback_manager=callback_manager,
    139         )
    140         tool_names = [tool.name for tool in tools]
    141         _output_parser = output_parser or cls._get_default_output_parser(llm=llm)
    142         return cls(
    143             llm_chain=llm_chain,
    144             allowed_tools=tool_names,
    145             output_parser=_output_parser,
    146             **kwargs,
    147         )
```

... with a LOT of args:

```
ipdb> args
cls = <class 'langchain.agents.structured_chat.base.StructuredChatAgent'>
llm = ChatOpenAI(client=<openai.resources.chat.completions.Completions object at 0x107a41430>, async_client=<openai.resources.chat.completions.AsyncCompletions object at 0x107a42b40>, root_client=<openai.OpenAI object at 0x1071e4fe0>, root_async_client=<openai.AsyncOpenAI object at 0x107a41460>, model_name='gpt-4', model_kwargs={}, openai_api_key=SecretStr('**********'))
tools = [TavilySearchResults(api_wrapper=TavilySearchAPIWrapper(tavily_api_key=SecretStr('**********')))]
callback_manager = None
output_parser = None
prefix = 'Respond to the human as helpfully and accurately as possible. You have access to the following tools:'
suffix = 'Begin! Reminder to ALWAYS respond with a valid json blob of a single action. Use tools if necessary. Respond directly if appropriate. Format is Action:```$JSON_BLOB```then Observation:.\nThought:'
human_message_template = '{input}\n\n{agent_scratchpad}'
format_instructions = 'Use a json blob to specify a tool by providing an action key (tool name) and an action_input key (tool input).\n\nValid "action" values: "Final Answer" or {tool_names}\n\nProvide only ONE action per $JSON_BLOB, as shown:\n\n```\n{{{{\n  "action": $TOOL_NAME,\n  "action_input": $INPUT\n}}}}\n```\n\nFollow this format:\n\nQuestion: input question to answer\nThought: consider previous and subsequent steps\nAction:\n```\n$JSON_BLOB\n```\nObservation: action result\n... (repeat Thought/Action/Observation N times)\nThought: I know what to respond\nAction:\n```\n{{{{\n  "action": "Final Answer",\n  "action_input": "Final response to human"\n}}}}\n```'
input_variables = None
memory_prompts = None
kwargs = {}
```

So the args passed to cls.create_prompt() et al seem to be the defaults of
`from_llm_and_tools`
which are in turn constants in the module
(`langchain/agents/structured_chat/base.py`
like `PREFIX` etc.

So, maybe i just want to call that class constructor?
It doesn't seem deprecated?

OR, the same default args are also defaults to cls.create_prompt()
so i could pass that as the recommended prompt to the recommended constructor function?


# Notes on using playwright to scrape - suggestions from Unnati Niraj Patel
(Recurse pairing partner 11/15/24)

- maybe consider using it to navigate to the page first
  - there's probably time-bound caching in eg URLs of XHR requests
- and then extract data from XHR requests
  - figure out the pattern of those


trace.playwright.dev is a site that can show you trace files recorded by playwright.

Consider using beautifulsoup to parse the HTML after navigating to the page, instead of playwright's own parsing?


# Levels.fyi info

A complete list of info from a levels.fyi entry - how much do i really need?

```
company:  Shopify
location: Montreal, QC, Canada
date: 3 days ago - OR - 11/03/2024
level: L6
role: Distributed Systems (Back-End)
years of experience: 7 yrs
years at company: 3 yrs
total comp: $167,961
base salary: $160.8k
stock: $7.2k
bonus: N/A
