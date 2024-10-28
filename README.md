# Problem 1: Automatic my recruiter email replies via gmail and RAG

Most of the recruiter mail I get is for positions that aren't a good match.
It's hard to find the good ones, and I don't want to spend a lot of time on it
manually.

I want to be able to reply to all of them quickly and politely. I want to use
RAG to generate appropriate (for me, based on my criteria!) replies to
recruiters, and then send them from my gmail account.

Is this a good time investment? Since it's an excuse to learn RAG
techniques on a practical problem I actually have, absolutely!

# Roadmap - reply client

- [x] Retrieve recruiter messages (and my replies) from gmail
- [x] Build a RAG chain trained on those messages
  - [x] Understand the parts of the chain that I don't yet!
  - [x] What is RunnablePassThrough?
  - [ ] Look at traces (where? langsmith?) and see if I can understand the chain
- [x] Try both claude and chatgpt, allow choosing 
- [x] Demo of generating replies based on example new messages
- [ ] Client: Retrieve new recruiter messages that I have *not* replied to
  - [ ] Solve problem of linkedin email that are recruiter followup, but gmail doesn't thread them
  - [ ] Solve messages that I've already replied to on linkedin and so aren't
        in gmail - maybe require manually re-labeling?
- [ ] Iterate on prompt against real recruiter email, until test replies to
      those usually look good
- [ ] Build a little UX allowing me to approve / edit / send replies
  - [ ] Decide on framework for this. Probably in browser
  - [ ] Streamlit?
  - [ ] Features:
    - [ ] Send as is
    - [ ] Edit and send
    - [ ] Skip
- [ ] Send replies
- [ ] Re-label replied messages, so it's easier to track what's done
- [ ] Work through the existing backlog with this tool
- [ ] Keep it at inbox zero until I get a job
- [ ] Profit


# Demo of current status

Trained on my previous replies, and running against hand-written synthetic
recruiter messages, it's pretty inconsistent so far.
But here's some not-terrible output:

```console
$ python demo.py --model=claude
Loaded 106 messages from cache
RAG setup complete
--------------------------------------------------------------------------------

New Recruiter Message (demo):
 I have a permanent role open for a senior staff python backend
developer who wants to learn AI. It pays $999k. The company is well
established, public, and is in NYC

Generated Reply:
 Hi there,  Thank you for reaching out with this exciting opportunity!
The role you've described aligns perfectly with my interests and
experience as a staff developer. I'm particularly intrigued by the
chance to learn AI while working on backend Python development.  The
compensation package is extremely attractive, and I appreciate that
it's a permanent position with a well-established public company. I'd
be very interested in learning more about the specific
responsibilities and challenges of the role.  Could we schedule a call
to discuss further details? I look forward to hearing from you.  Best
regards, Paul


--------------------------------------------------------------------------------

New Recruiter Message (demo):
 Hey Paul! Come work for me in San Francisco! Regards, Jobby McJobface

Generated Reply:
 Hi Jobby,  Thank you for reaching out about the opportunity in San
Francisco. While I appreciate your interest, I'm currently only
considering positions in NYC or fully remote roles. My experience as a
staff developer might be valuable to your team, but the location
doesn't align with my current preferences. If you have any remote
opportunities that match my skills, I'd be happy to learn more.  Best
regards, Paul


--------------------------------------------------------------------------------

New Recruiter Message (demo):
 Hi are you available for a call tomorrow? I have a great opportunity
for a junior full stack engineer.

Generated Reply:
 Hi there,  Thank you for reaching out. I appreciate the opportunity,
but I'm not a good fit for a junior full stack role. I have 24 years
of experience and was most recently in a staff developer position.
Additionally, full stack development isn't my primary focus.   I'm
open to senior or staff-level backend engineering roles in NYC or
fully remote, with compensation comparable to my previous position at
Shopify (**REDACTED** annual). If you have any opportunities matching
these criteria, I'd be happy to discuss further.  Best regards, Paul


--------------------------------------------------------------------------------

New Recruiter Message (demo):
 Hello, would you be interested in a contract position? It pays $35 per
hour.

Generated Reply:
 Hello,  Thank you for reaching out about this opportunity.
Unfortunately, the compensation for this contract position is not in
line with my current expectations. For reference, I was previously
earning **REDACTED** total annual compensation at Shopify. Given my 24 years
of experience as a staff developer, I'm primarily focusing on roles at
established tech companies that can offer competitive compensation and
responsibilities. If you have any positions that might better align
with my background and expectations, please let me know.  Best
regards, Paul


--------------------------------------------------------------------------------

New Recruiter Message (demo):
 Hi there! I came across your profile and was impressed by your
experience. We have an exciting opportunity for a Senior Software
Engineer position. Would you be interested in learning more?

Generated Reply:
 Hello,  Thank you for reaching out about the Senior Software Engineer
position. I'm interested in learning more about the role and company.
Could you provide details on the challenges, responsibilities, and
compensation? I've been focusing on staff-level backend roles at
established tech companies. For reference, my previous total annual
compensation at Shopify was **REDACTED**. Please let me know if this aligns
with your offering. I look forward to hearing more.  Best regards,
Paul
```

# Problem 2: Research agent

Researching companies is time consuming and tedious.
Data entry into my spreadsheet is tedious.
Can RAG or other AI techniques help automate this?

## Research agent roadmap

- [x] Proof of concept RAG agent
  - [x] Try with both anthropic and openai
  - [x] Try RecursiveUrlLoader to fetch more data from company websites
        ... this is not helping much; we're downloading entire websites and not
        finding the information we want. Hard to verify if it's even present.
      - [ ] Try again with a "known good" website, ie one where I know what info to expect?
  - [ ] Try with Tavily search
      - [ ] Lots of decisions to make here per https://blog.langchain.dev/weblangchain/
- [x] formalize my research steps
  - [x] General info
    - [x] company name
    - [ ] mission statement ... unreliable results so far
    - [ ] headcount size (total, eng, NYC) ... no reliable results so far
    - [x] funding / public status
    - [x] remote policy (remote / hybrid / onsite)
    - [ ] headquarters location
    - [x] chatgpt seems to be quite good at this, given company URL - but
          unreliable via API, use RAG as per website-questioner demo.
    - [x] tell it to format result as json, it's also good at this
  - [ ] role specifics from email, if any
    - [ ] include link from email if any in web searches
  - [ ] levels.fyi - use some browser driver for this? i need to be logged in
    - [ ] comparative level
    - [ ] salary - iterative search
      - [ ] base
      - [ ] RSU
      - [ ] bonuses
      - [ ] vesting schedule
- [ ] Dump this all into google sheet


Instant proof of concept from chatgpt interactive:

Prompts I tried:
```
What is the funding status of this company? https://www.rokt.com/ 

(response skipped)

how many employees does rokt have, and as of what date?

(response skipped)

What is their remote work policy? Please give the result along with the previous info in the form of this JSON response, where the items in brackets are placeholders

{"name":  <company name>,  "public":  <boolean>, "headquarters": <city>, "size estimate": <int>,  "work policy":  <hybrid|remote|full onsite> } 
```

Response to the last prompt:

```
Here is the requested JSON response for Rokt:
```
```json
{
  "name": "Rokt",
  "public": false,
  "headquarters": "New York City",
  "size estimate": 600,
  "work policy": "hybrid"
}
```

```
Rokt is a private company headquartered in New York City with approximately 600 employees. Their work policy is hybrid, requiring employees to work onsite for at least three days a week​
```
