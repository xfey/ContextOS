# ContextOS

**[中文](README_cn.md) | English**

[Highlights](#highlights) | [Quick Start](#quick-start) | [Architecture](#architecture) | [Contributing](#contributing) | [🌐 Website](https://xfey.github.io/ContextOS/)

The first **AI-Centric** Proactive Agent Framework — transforming AI from "waiting for commands" to "actively serving".

![ContextOS Demo](docs/demos/demo.gif)

Try the demo app built on ContextOS: **Zero-step Clipboard**

- Download `.dmg` file: [Releases](https://github.com/xfey/ContextOS/releases)
- How to use: [Installation Guide](#installation-guide)


## Highlights

ContextOS introduces an AI-centric approach to intelligent agents. Instead of following human-defined workflows, the AI itself becomes the center of decision-making. By providing maximum autonomy and rich context, ContextOS creates a fundamentally different kind of agent.

This agent continuously collects signals, understands user intent, and proactively offers help at the right moment. For example, when a user copies a long piece of foreign text, ContextOS guesses that translation is needed and automatically notifies the user with the result. Unlike traditional agents that require users to explicitly ask questions, ContextOS takes AI assistance one step further.

The goal is to provide a clear and extensible framework that gives large language models more context and freedom, enabling smarter Agentic AI. Built on this foundation, a simple demo called "Smart Clipboard" has been created: it supports text, images, and mixed inputs, allowing AI to provide help based on the content.


## Quick Start

### System Requirements

- **Operating System**: macOS 12.0 or later
- **API Key**: Any LLM API key compatible with OpenAI interface
- **Model Requirements**:
  - For image support: Use vision models (e.g., `gpt-4o`, `qwen3-vl-flash`)
  - For text-only tasks: Standard models work fine (e.g., `gpt-5-mini`, `qwen-plus`)

### Installation Guide

1. Open the downloaded `.dmg` file and drag ContextOS to the Applications folder
2. Wait a moment, then find the ContextOS icon in Launchpad
3. Grant permissions when prompted
   > ContextOS needs clipboard access to provide context-aware assistance
4. If you see "App blocked from opening", go to System Settings → Privacy & Security and click Allow
5. Before first use, configure a valid LLM API key and set your preferred language

### Configure LLM API

ContextOS uses the OpenAI API format. Keep the `Provider` field as `OpenAI` (default), then configure:

- `Base URL`: API endpoint address, usually starts with `https`
- `Model`: Model name, e.g., `gpt-4o` or `qwen3-vl-flash`
- `API Key`: Your API key string

### Model Recommendations

- **For users in China**: `qwen3-vl-flash` (Qwen offers free quota, fast response, supports images)
- **Other options**: Try various models from [OpenRouter](https://openrouter.ai/)

**Tip**: Choose "faster" over "larger" models. Lower latency significantly improves user experience.

After setup, the system will automatically verify your API key. If network issues cause failures, try again.

### Build ContextOS

For developers, you can just run `bash build.sh` to build this project on your own. Try it!


## Architecture

![flow chart](docs/dataflow.png)

ContextOS consists of four main modules:

- **Data Source**: Collects raw data from various sources. Data sources include **events** (discrete signals like clipboard updates) and **streams** (continuous data like screen captures).

- **Intent Engine**: Detects user intent based on data features and classifies the type of intent.

- **Agent Engine**: Uses the ReAct architecture, executing tasks through "Thought-Action-Observation" loops. The AI reasons based on user intent, calls tools, observes results, and iterates until the task is complete.

- **Interface**: Renders the user interface and manages session state. Users receive notifications through the Inbox and can interact with the system. Based on task complexity, two interaction modes are available: Notify (auto-complete) and Review (multi-turn conversation).

### Design Principles

ContextOS aims to be a clear and extensible architecture. Key design features include:

- **Clear data flow**: Adapters collect data → Engine handles intent recognition and task execution → Interface manages interaction
- **Easy to extend**: Simple adapter and tool interfaces — just implement core functions to add new capabilities
- **Unified prompt management**: All prompt files are organized in a dedicated folder for easy updates
- **Extensible configuration**: Tool and data source configs are simple and clear

The hope is that developers will build on ContextOS to create more features and advance the "AI-centric" agent paradigm. Here are some practical examples:

**Adding new data sources**: Beyond the currently active clipboard, the project already includes screen capture support in [./adapters/stream/screenshot.py]. Extending to more sources is straightforward — just implement a few key functions.

**Adding new tools**: To reduce API key management complexity, only basic tools are implemented. In `integrations/`, you can see that tools only need to implement `schema` and `execute` methods — very easy to add.

**Do you need a UI?**: The visual interface quickly demonstrates ContextOS's capabilities. If you only need the core flow as a backend, you can skip the complex `interfaces` module and keep just the core data pipeline.

### Current Limitations

ContextOS is still a work in progress. Some challenges encountered during development:

**UI Complexity**: Defining core data structures took relatively little time, but most effort and code went into building the user interface. As a simple demo, the goal was to provide a good user experience while promoting the "AI-centric" agent design philosophy.

**Incomplete Features**: More tools and data sources haven't been added yet. Support for MCP servers and memory systems is also not implemented.


## Contributing

Feel free to contribute to ContextOS and help build "AI-centric" agents!

You can contribute by:
- Extending ContextOS with new features or more effective prompts
- Finding and fixing bugs
- Improving extensibility and other aspects of the framework

If you or your organization would like to provide free API keys for more users to experience ContextOS and related products, that would be greatly appreciated!

Welcome any friendly discussion!

Email: xfey99@gmail.com
