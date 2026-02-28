from autogen_core.tools import FunctionTool

async def my_func_wrapper():
    pass

try:
    tool = FunctionTool(my_func_wrapper, name="run_code", description="test")
    print("Tool name with kwarg is:", tool.name)
except Exception as e:
    import traceback
    traceback.print_exc()

# Let's see if there's a different way
