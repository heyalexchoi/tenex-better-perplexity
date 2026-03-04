# USER REPORTED ISSUES
[ ] display logic should be consistent between active run, and after run is completed.
[ ] display of tool and chat messages inside UI chat bubble should be chronological. For example, if assistant sends chat message, then launches browser agent that takes 3 steps, then chat agent sends final message, those messages should all be displayed in order: chat 1, browser step 1, browser step 2, browser step 3, chat 2.
[ ] we should have more readable display for browser step messages. 
    example: "browser_use_step: Step 1: root=SearchActionModel(search=SearchAction(query='chigga history meaning definition', engine='duckduckgo')) about:blank" should be 'Searched: "chigga history meaning definition"'. We can discuss how to best do this - does the browser agent hook output objects or strings? or json strings?
[ ] get rid of app/ wrapper and update references to starting app to start server.
