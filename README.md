# What: Automatic my recruiter email replies via gmail and RAG

Most of the recruiter mail I get is for positions that aren't a good match.
It's hard to find the good ones, and I don't want to spend a lot of time on it
manually.

I want to be able to reply to all of them quickly and politely. I want to use
RAG to generate appropriate (for me, based on my criteria!) replies to
recruiters, and then send them from my gmail account.

Is this a good time investment? Since it's an excuse to learn RAG
techniques on a practical problem I actually have, absolutely!

# Roadmap

- [x] Retrieve recruiter messages (and my replies) from gmail
- [x] Build a RAG chain trained on those messages
  - [ ] Understand the parts of the chain that I don't yet!
  - [ ] What is RunnablePassThrough? 
  - [ ] Look at traces (where? langsmith?) and see if I can understand the chain
- [x] Try both claude and chatgpt, allow choosing 
- [x] Demo of generating replies based on example new messages
- [ ] Retrieve new recruiter messages that I have *not* replied to
  - [ ] Solve problem of linkedin email that are recruiter followup, but gmail doesn't thread them
  - [ ] Solve messages that I've already replied to on linkedin and so aren't in gmail
- [ ] Iterate on prompt against real recruiter email, until test replies to
      those usually look good
- [ ] Build a little UX allowing me to approve / edit / send replies
- [ ] Send replies
- [ ] Re-label replied messages, so it's easier to track what's done
- [ ] Work through the existing backlog with this tool
- [ ] Keep it at inbox zero until I get a job
- [ ] Profit


# Demo of current status

Trained on my previous replies, and running against hand-written synthetic
recruiter messages, it's pretty inconsistent so far.
Here's some not-terrible output:

```
New Recruiter Message (demo):
 Hey Paul! Come work for me in San Francisco! Regards, Jobby McJobface

Generated Reply:
 Hi Jobby,  Thank you for reaching out about the opportunity in San
Francisco. While I appreciate your interest, I'm currently only
considering positions in NYC or fully remote roles. My experience as a
staff developer might be valuable to your team, but the location
doesn't align with my current preferences. If you have any remote
opportunities that match my background, I'd be happy to learn more.
Best regards, Paul
```

```
New Recruiter Message (demo):
 Hi are you available for a call tomorrow? I have a great opportunity
for a junior full stack engineer.

Generated Reply:
 Hi there,  Thank you for reaching out. I appreciate the opportunity,
but I'm not currently seeking junior or full stack roles. With 24
years of experience and having held a staff developer position, I'm
focusing on senior or staff-level backend engineering roles.
Additionally, my expertise isn't in full stack or JavaScript
development.  I'm open to opportunities in NYC or fully remote, with
compensation comparable to my previous role at Shopify (*REDACTED* total
annual). If you have any positions matching these criteria, I'd be
happy to discuss further.  Best regards, Paul
```
