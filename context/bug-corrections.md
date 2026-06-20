# Bug Fixes
1. ✅ FIXED (2026-06-06) — When kicking off additional research with the "Research this" prompt in the RAG chat screen, there is no indicator that the research is in progress. Can we please get some kind of UI indicator there.

2. New chat messages don't appear automatically, I have to refresh the page every time in order to see it. I would like the messages to populate on screen as soon as they are available Or potentially a polling solution like we have on other parts of this project 

3. I want the text input for the chat tab to automatically expand to fit my text so that I can see the whole message or at least scroll through the whole message easily before I send.

4. It seems like the chatbot is trying to quote sources, but it's not properly able to link them. The links are properly showing in the dedicated section for sources at the bottom of the message, but within the message itself from the AI, it's including what looks like attempts at inline quotes and sourcing, which are not working. 

# Major Features to add
1. I want to have a stress test feature where we take a report that's been built and then go try to find disproving evidence. I want to have two modes for this: One where it's entirely the LLM making the decision about what questions to ask and what things to poke holes in, and another where it's me, the user, deciding what questions to ask and what things to poke holes in.

2. I would like to add token streaming to the RAG chat screen

3. I want an organization system for my research projects. Perhaps a folder system? Ask me some questions to get clarity on this, and then let's implement it. 

4. ✅ FIXED (2026-06-19) — Source selection moved from Report screen to Sources screen. Each SourceCard now has a checkbox; Select all / Deselect all + 25-source cap enforced; instructions + Generate report + Auto-draft controls sit in an inline panel at the bottom of the Sources screen. Clicking Generate report navigates to the Report screen. The Report screen is now view-only: shows the report, a "Generating…" state, or "No report yet." 