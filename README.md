# Problem 1: Automatic my recruiter email replies via gmail and RAG

Most of the recruiter mail I get is for positions that aren't a good match.
It's hard to find the good ones, and I don't want to spend a lot of time on it
manually.

I want to be able to reply to all of them quickly and politely. I want to use
RAG to generate appropriate (for me, based on my criteria!) replies to
recruiters, and then send them from my gmail account.

Is this a good time investment? Since it's an excuse to learn RAG
techniques on a practical problem I actually have, absolutely!

# Problem 2: Research agent

Researching companies is time consuming and tedious.
Data entry into my spreadsheet is tedious.
Can RAG or other AI techniques help automate this?

I have a pretty standard set of questions I want answered about companies I'm
researching. Some of them are amenable to answering in a predictable way
(eg on Linkedin or Levels); some take more exploratory digging (eg "How many
people work there?" or "What's their remote/onsite work policy?")

# Notes on workflow

I'd like this to suit me being able to deal with a batch of possible jobs
(whether found via email, tips from elsewhere, whatever) in a fairly natural
way.
Eg:

- Walk up to my computer
- Run `<the program>`
  - See some kind of summary of status, TBD
  - for example: "There are 9 un-responded recruiter pings from linkedin"
- Automated research happens
  - by default, do all un-researched companies?
- List of results and action items
  - "company foo via linkedin ping"
  - actions: reply (auto w/ confirmation), defer / do nothing, archive / ignore

"Defer" raises a question of state.
Do we need some kind of db tracking status?
(Or maybe the cache is enough)


# Roadmap, end to end


- [x] Build main end-to-end script that integrates all of the below
- [x] Email client
  - [x] Retrieve recruiter messages (and my replies) from gmail
  - [x] Build a RAG chain trained on those messages
    - [x] Understand the parts of the chain that I don't yet!
    - [x] What is RunnablePassThrough?
    - [ ] Look at traces (where? langsmith?) and see if I can understand the chain
  - [x] Try both claude and chatgpt, allow choosing 
  - [x] Demo of generating replies based on example new messages
  - [ ] Solve problem of linkedin email that are recruiter followup, but gmail doesn't thread them
  - [ ] Solve messages that I've already replied to on linkedin and so aren't in gmail - maybe require manually re-labeling
  - [ ] Iterate on prompt against real recruiter email, until test replies to those usually look good.
?
  - [ ] Extract data from attachments if any (eg .doc or .pdf)
  - [ ] Extract subject from message too
- [x] Build a little UX allowing me to approve / edit / send replies
    - [ ] They should be batched! See "Notes on workflow"
    - [x] Decide on framework for this. Could be in browser, or just command
          line. Streamlit?
    - [x] Chose command line for first pass
      - [x] Edit reply        
    - [x] Chose SPWA using Alpine.js and Pico.css for second pass
    - [ ] Features needed:
      - [ ] List companies
        - [ ] Display known data
        - [ ] Link to original message, if any (maybe just gmail link?)
        - [ ] "Generate reply" button (or "regenerate")
        - [ ] Display reply
        - [ ] "Edit reply" link
        - [ ] "Send and archive" button
      - [x] Edit reply
      - [ ] Confirm reply or skip
- [ ] Actually send email replies
- [ ] Re-label replied messages (so we know they don't need looking at again)
- [ ] Company research: general info
  - [x] Formalize my research steps:
  - [x] Try langchain with both anthropic and openai
  - [x] Try RecursiveUrlLoader to fetch more data from company websites
        ... this is not helping much; we're downloading entire websites and not
        finding the information we want. Hard to verify if it's even present.
  - [x] Try with Tavily search
    - [x] Lots of decisions to make here per https://blog.langchain.dev/weblangchain/
    - [ ] Report Tavily issue: Undocumented 400 character limit on get_search_context(query). Client gets a 400 error, but no indication of what's wrong.
    - [x] Tavily works great, using that!
- [x] Data model for company info (name, headcount size, funding/public status,
      remote policy, etc)
  - [x] Derive fields from my google spreadsheet
  - [x] chose Pydantic, it's pretty nice
- [x] Write a Google sheet client to store this data model in my existing sheet
  - [x] Integrate with main script
  - [ ] Check if company already exists in sheet; if so, update rather than add
- [x] Company research: Salary data from levels.fyi
  - [x] Drive browser - chose Playwright
  - [x] Extract salary data based on company name
  - [x] Extract job level comparable to Shopify staff eng
  - [x] Integrate salary with main script, add to spreadsheet
  - [x] Integrate level with main script, add to spreadsheet
- [ ] Main End-to-end script: decide whether the company is a good fit, yes/no
- [x] Company research: Find contacts in linkedin search
  - [x] Drive browser
  - [x] Search for 1st degree connections currently at company
  - [x] Integrate with end-to-end flow, add to spreadsheet
  - [ ] Skip if company not a good fit
- [ ] Company research: Find contacts in recurse
  - [ ] Is there an API? Or drive browser? Is there TOS?
  - [ ] Search for 1st degree connections currently at company
  - [ ] Integrate with end-to-end flow, add to spreadsheet
  - [ ] Skip if company not a good fit
- [ ] Work through the existing backlog with this tool
- [ ] Keep it at inbox zero until I get a job
- [ ] Profit


## Tavily strategy: One big prompt or multiple?

I wasn't sure which way to go and experimenting was inconclusive. 
So I asked Tavily! (And chatgpt and claude.)

Prompt and responses are in
tavily-prompt-strategy.md

TL;DR consider a hybrid approach of a few strategically related prompts.
