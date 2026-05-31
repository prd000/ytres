There is a context folder within the root folder of this project that is going to give you all the information that you need in order to be able to begin contributing to this project.

The PRD is a project requirements document. The DESIGN.md is the design document outlining the design philosophy of this project. Bug corrections is a file of the bugs that we're currently working on fixing or features that we're looking to add. And the log.md is just the update of all the things that we have built so far. The map file is a file map of the entire project, including functionality for each file so you know where to look. Decisions.md tracks big architectural changes or any decisions that we make that would differ from what you see in the PRD document. Deferred work is things that need to be implemented by the user, or we are deferring in favor of getting a working prototype, et cetera -it is where we track things that we need to do later. 

Anytime you make a change to the codebase always update the log.md file.

Any time you update anything that the user will see on the UI or UX, always reference the design.md document.

If you ever use dummy data or need an API key that you don't yet have an environment variable for, always add that to the deferredwork.md document in the context folder. Alert the user to any additions to deferred work.

Any time you and the user come to a decision about the direction of the project or architectural changes, Add it to the Decisions.md file. 

Before making any changes, read the decisions.md file and PRD.md file to make sure it aligns with the architecture that we've laid out And the vision we have for the project

When making changes that require edits to both backend and frontend, edit the backend first, then wire it up to the frontend. 

When fixing bugs, always use robust testing and logging to identy and confirm issues as well as fixes

Avoid hard-coding wherever it makes sense - best practice is to have a layer or more of abstraction to maintain modularity, making it easy to adjust code as needed and keep the codebase human readable