Add following env variables:
- GEMINI_API_KEY, DEEP_SEEK_API_KEY, LOCAL_LLM_API_KEY, LOCAL_LLM_API_URL


Run server: 
```cd server && uvicorn main:app --port 5000 --reload```


TODOs:
1. Add openai client
2. Add qwen client
3. Test qidian.com :D
4. Add progress bar for translate btn