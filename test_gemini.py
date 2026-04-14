import asyncio
import os
import sys

# Ensure project root is in python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.services.llm_analyst import LLMAnalyst

async def main():
    try:
        analyst = LLMAnalyst()
        print(f"=====================================")
        print(f"Testing Gemini Configuration:")
        print(f"Model: {analyst.us_model}")
        print(f"Base URL: {analyst.us_base_url}")
        print(f"=====================================\n")
        
        print("Sending test request to Gemini...")
        stream = await analyst.us_client.chat.completions.create(
            model=analyst.us_model,
            messages=[
                {"role": "user", "content": "你是一个金融量化分析师。请用50个字左右简短生成一份测试研报，证明你目前可以正常工作并连接成功。"}
            ],
            max_tokens=200,
            temperature=0.7,
            stream=True,
            timeout=30.0
        )
        
        print("Response: ", end="")
        full_content = ""
        async for chunk in stream:
            content = chunk.choices[0].delta.content
            if content:
                full_content += content
                print(content, end="", flush=True)
        
        print("\n\n✅ Gemini 2.5 Pro is working successfully!")
        
    except Exception as e:
        import traceback
        print(f"\n❌ Request failed!")
        print(f"Error Details: {str(e)}")
        print("Traceback:")
        print(traceback.format_exc())

if __name__ == "__main__":
    asyncio.run(main())