Model Context Protocol

Connect external tools and data sources to Cursor using the Model Context Protocol (MCP) plugin system
​
What is MCP?

The Model Context Protocol (MCP) is an open protocol that standardizes how applications provide context and tools to LLMs. Think of MCP as a plugin system for Cursor - it allows you to extend the Agent’s capabilities by connecting it to various data sources and tools through standardized interfaces.
Learn More About MCP

Visit the official MCP documentation to understand the protocol in depth
​
Uses

MCP allows you to connect Cursor to external systems and data sources. This means you can integrate Cursor with your existing tools and infrastructure, instead of having to tell Cursor what the structure of your project is outside of the code itself.

MCP servers can be written in any language that can print to stdout or serve an HTTP endpoint. This flexibility allows you to implement MCP servers using your preferred programming language and technology stack very quickly.
​
Transport

MCP servers are lightweight programs that expose specific capabilities through the standardized protocol. They act as intermediaries between Cursor and external tools or data sources.

Cursor supports three transport types for MCP servers:
Transport	Execution environment	Deployment	Users	Input	Auth
stdio	Local	Cursor manages	Single user	Shell command	Manual
SSE	Local/Remote	Deploy as server	Multiple users	URL to an SSE endpoint	OAuth
Streamable HTTP	Local/Remote	Deploy as server	Multiple users	URL to an HTTP endpoint	OAuth

Each transport type has different use cases, with stdio being simpler for local development and SSE/Streamable HTTP offering more flexibility for distributed teams.
​
Installing MCP Servers
​
One-Click Installation

You can now set up MCP servers in Cursor with one click! We’ve curated a collection of popular MCP servers that you can install instantly with OAuth support for quick authentication.
Browse MCP Tools

Explore our curated collection of MCP servers and install them with one click

For MCP developers, you can make your server easily accessible to users by adding an “Add to Cursor” button to your documentation:
Add to Cursor Button

Learn how to create an “Add to Cursor” button for your MCP server
​
Manual Configuration

For custom MCP servers or advanced configurations, you can manually set up MCP servers using the configuration file approach below.

The MCP configuration file uses a JSON format with the following structure:
Copy
Ask AI

// This example demonstrated an MCP server using the stdio format
// Cursor automatically runs this process for you
// This uses a Node.js server, ran with `npx`
{
  "mcpServers": {
    "server-name": {
      "command": "npx",
      "args": ["-y", "mcp-server"],
      "env": {
        "API_KEY": "value"
      }
    }
  }
}

The env field allows you to specify environment variables that will be available to your MCP server process. This is particularly useful for managing API keys and other sensitive configuration.
​
Configuration Locations

You can place this configuration in two locations, depending on your use case:
Project Configuration

For tools specific to a project, create a .cursor/mcp.json file in your project directory. This allows you to define MCP servers that are only available within that specific project.
Global Configuration

For tools that you want to use across all projects, create a ~/.cursor/mcp.json file in your home directory. This makes MCP servers available in all your Cursor workspaces.
​
Authentication

MCP servers can be provided with environment variables to authenticate with. This allows you to provide API keys and other authentication tokens to the MCP server, without exposing them in your code or storing them within the MCP server itself.

Cursor also supports OAuth authentication for MCP servers that require it, enabling secure access to external services without manually managing tokens.
​
Using MCP in Chat

The Composer Agent will automatically use any MCP tools that are listed under Available Tools on the MCP settings page if it determines them to be relevant. To prompt tool usage intentionally, simply tell the agent to use the tool, referring to it either by name or by description. You can also enable or disable individual MCP tools from the settings page to control which tools are available to the Agent.
​
Tool Approval

By default, when Agent wants to use an MCP tool, it will display a message asking for your approval. You can use the arrow next to the tool name to expand the message, and see what arguments the Agent is calling the tool with.

​
Auto-run

You can enable auto-run to allow Agent to automatically run MCP tools without requiring approval, similar to how terminal commands are executed. Read more about Yolo mode and how to enable it here.
​
Tool Response

When a tool is used Cursor will display the response in the chat. This image shows the response from the sample tool, as well as expanded views of the tool call arguments and the tool call response.

​
Image Injection

When using some MCP servers, Cursor may run a tool that returns an image, such as a screenshot of a website, or a diagram. To allow the Chat to properly view and use the images in it’s replies, you can ensure the server is configured to return the image in the correct format.

To do this, you can simply return a base64 encoded string of the image in the tool response.
Copy
Ask AI

const RED_CIRCLE_BASE64 = "/9j/4AAQSkZJRgABAgEASABIAAD/2w..." 
// ^ full base64 clipped for readability

server.tool("generate_image", async (params) => {
  return {
    content: [
      {
        type: "image",
        data: RED_CIRCLE_BASE64,
        mimeType: "image/jpeg",
      },
    ],
  };
});

A full example of an MCP server that returns an image can be found here.

By returning the image in this format, Cursor will attach the image into the chat, and if the current model supports it, the image will be viewed and analyzed by the model to help with the it’s next steps.
​
Limitations

MCP is a very new protocol and is still in active development. There are some known caveats to be aware of:

Tool Quantity

Some MCP servers, or user’s with many MCP servers active, may have many tools available for Cursor to use. Currently, Cursor will only send the first 40 tools to the Agent.

Remote Development

Cursor directly communicates with MCP servers from your local machine, either directly through stdio or via the network using sse. Therefore, MCP servers may not work properly when accessing Cursor over SSH or other development environments. We are hoping to improve this in future releases.

MCP Resources

MCP servers offer two main capabilities: tools and resources. Tools are available in Cursor today, and allow Cursor to execute the tools offered by an MCP server, and use the output in its further steps. However, resources are not yet supported in Cursor. We are hoping to add resource support in future releases.