# USER REPORTED ISSUES
[ ] currently front end keeps hitting /api/sessions/id/stream?auth=tenex123%21 over and over at 404. should password really be a query param? 
[ ] front end input seems broken. maybe downstream from above problem.
[ ] seems that the browser agent result is "Browser task completed" to the chat agent. it should be the browser agent's final result. a detailed report of it's findings so that chat agent can give answer to user, and answer any follow up questions on findings.
[ ] display logic should be consistent between active run, and after run is completed.
[ ] display of tool and chat messages inside UI chat bubble should be chronological. For example, if assistant sends chat message, then launches browser agent that takes 3 steps, then chat agent sends final message, those messages should all be displayed in order: chat 1, browser step 1, browser step 2, browser step 3, chat 2.
[ ] we should have more readable display for browser step messages. 
    example: "browser_use_step: Step 1: root=SearchActionModel(search=SearchAction(query='chigga history meaning definition', engine='duckduckgo')) about:blank" should be 'Searched: "chigga history meaning definition"'. We can discuss how to best do this - does the browser agent hook output objects or strings? or json strings?
[ ] get rid of app/ wrapper and update references to starting app to start server.
