---
name: gitcode-api-handler
description: Handles GitCode API requests based on local API documentation. Invoke when user needs to call GitCode APIs, construct API requests, or execute API operations.
---

# GitCode API Handler

This skill helps you construct and execute GitCode API requests based on the local API documentation.

## Purpose

- Read and parse local GitCode API documentation
- Construct properly formatted API requests
- Handle authentication (access_token)
- Execute API calls and process responses
- Provide code examples in multiple languages
- Validate request parameters against documentation

## When to Invoke

**Invoke this skill when:**
- User wants to call a GitCode API endpoint
- User needs help constructing an API request
- User asks about GitCode API usage or parameters
- User mentions "GitCode API", "call API", "API request", or similar requests
- User needs to perform operations on GitCode (create repo, manage issues, etc.)

## Prerequisites

This skill comes with complete GitCode API documentation built-in. No additional setup required.

The built-in documentation is located at:
```
./references/
├── INDEX.md                    # Global API index
├── Branch.md                   # Branch API overview
├── Branch/                     # Branch API detailed docs
│   ├── create-branch.md
│   ├── delete-branch.md
│   ├── get-branch.md
│   └── ...
├── Commit.md                   # Commit API overview
├── Commit/                     # Commit API detailed docs
├── Issues.md                   # Issues API overview
├── Issues/                     # Issues API detailed docs
├── Labels.md                   # Labels API overview
├── Labels/                     # Labels API detailed docs
├── PullRequests.md             # Pull Requests API overview
├── PullRequests/               # Pull Requests API detailed docs
├── Release.md                  # Release API overview
├── Release/                    # Release API detailed docs
├── Repositories.md             # Repositories API overview
├── Repositories/               # Repositories API detailed docs
├── Search.md                   # Search API overview
├── Search/                     # Search API detailed docs
├── Tag.md                      # Tag API overview
└── Tag/                        # Tag API detailed docs
```

## API Coverage

The built-in documentation includes **154 API endpoints** across 9 categories:

| Category | API Count | Description |
|----------|-----------|-------------|
| **Pull Requests** | 44 | PR creation, merging, comments, testing, review |
| **Repositories** | 36 | File operations, settings, permissions, Fork |
| **Issues** | 26 | Issue creation, queries, comments, labels |
| **Commit** | 12 | Commit queries, comments, statistics |
| **Labels** | 9 | Label creation, updates, deletion |
| **Branch** | 8 | Branch creation, deletion, protection rules |
| **Tag** | 8 | Tag creation, deletion, protection rules |
| **Release** | 8 | Release creation, update, query, attachment management |
| **Search** | 3 | User, repository, and Issue search |

## Documentation Features

Each API documentation includes:
- **HTTP Method**: GET, POST, PUT, PATCH, DELETE
- **API Path**: Complete endpoint path with parameters
- **Parameters**: Path, query, and body parameters with types
- **Response Structure**: Complete response field descriptions
- **Examples**: cURL and Python examples
- **Error Handling**: Common error codes and messages

## Input Requirements

- **API Name or Description**: Which API to call (e.g., "create repository", "list branches")
- **Parameters**: Required and optional parameters for the API
- **Authentication**: GitCode access token (if not provided, will ask user)
- **Base URL**: GitCode API base URL (default: `https://api.gitcode.com/api/v5`)

## Execution Steps

### Step 1: Identify the API Endpoint

**CRITICAL: Always try to read INDEX.md files first before searching individual API files.**

#### 1.1 Check for Global INDEX.md

Read the global INDEX.md:
```
.trae/skills/gitcode-api-handler/references/INDEX.md
```

This file contains:
- Overview of all API categories
- Links to category-specific documentation
- Quick reference to available endpoints
- Total API count and statistics

#### 1.2 Check for Category INDEX.md

If the user mentions a specific category (e.g., "Branches", "Issues"), read the category overview:
```
.trae/skills/gitcode-api-handler/references/{Category}.md
```

This file contains:
- List of all APIs in this category
- Quick reference table with methods and paths
- Brief descriptions of each endpoint
- Request examples for common operations

#### 1.3 Use INDEX for Quick Lookup

**When INDEX.md exists:**
1. Parse the INDEX.md to find matching API
2. Extract the API documentation file path from the index
3. Read the specific API documentation file directly
4. Skip the broader searchCodebase search

**Benefits:**
- Faster API lookup
- More accurate endpoint matching
- Better organization and navigation
- Reduced file system operations

#### 1.4 Fallback to Search (If INDEX.md Not Found)

If INDEX.md doesn't exist:
1. Search local documentation for the requested API
2. Match user's description to available endpoints
3. Read the specific API documentation file

#### 1.5 Extract API Details

From the API documentation file, extract:
- HTTP method (GET/POST/PUT/DELETE/PATCH)
- API path
- Required parameters
- Optional parameters
- Request body structure
- Response structure

### Step 2: Validate Parameters

1. Check all required parameters are provided
2. Validate parameter types against documentation
3. Check for parameter constraints (enums, ranges, etc.)
4. Warn about missing optional parameters that might be useful

### Step 3: Construct the Request

Build the complete API request:

**URL Construction:**
```
{base_url}{path}?{query_params}
```

**Path Parameters:**
- Replace `:owner`, `:repo`, etc. with actual values

**Query Parameters:**
- Add `access_token` for authentication
- Add other query parameters as needed

**Request Body:**
- Construct JSON body for POST/PUT/PATCH requests
- Include all required fields
- Include optional fields if provided

### Step 4: Generate Request Examples

Provide examples in multiple formats:

**cURL:**
```bash
curl -X {METHOD} "{url}?access_token=YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{request_body}'
```

**Python (requests):**
```python
import requests

url = "{url}"
params = {"access_token": "YOUR_TOKEN"}
data = {request_body}

response = requests.{method}(url, params=params, json=data)
print(response.json())
```

### Step 5: Execute the Request (Optional)

If user requests execution:
1. Use WebFetch or RunCommand to execute the request
2. Parse the response
3. Display results in a user-friendly format
4. Handle errors gracefully

## Authentication

GitCode API requires authentication via `access_token`:

**Methods:**
1. **Query Parameter**: `?access_token=YOUR_TOKEN`
2. **Header**: `Authorization: Bearer YOUR_TOKEN`
3. **Header**: `PRIVATE-TOKEN: YOUR_TOKEN`

**Token Sources:**
- User's personal access token from GitCode settings
- Environment variable: `GITCODE_ACCESS_TOKEN`
- Configuration file: `.gitcode-config.json`

**Security:**
- Never hardcode tokens in code
- Always use environment variables or secure storage
- Warn users about token security

## Common API Categories

### Repositories
- List repositories
- Create repository
- Get repository details
- Update repository
- Delete repository

### Branches
- List branches
- Create branch
- Get branch details
- Delete branch
- Set branch protection

### Issues
- List issues
- Create issue
- Get issue details
- Update issue
- Close/reopen issue

### Pull Requests
- List pull requests
- Create pull request
- Get PR details
- Merge pull request

### Release
- Create release
- Get release details
- Update release
- Download attachments

## Response Handling

### Success Response
- Parse JSON response
- Display relevant fields
- Show pagination info if applicable

### Error Response
```json
{
  "message": "Error description",
  "errors": [...]
}
```

**Common Error Codes:**
- 400: Bad Request - Invalid parameters
- 401: Unauthorized - Invalid or missing token
- 403: Forbidden - Insufficient permissions
- 404: Not Found - Resource doesn't exist
- 409: Conflict - Resource already exists
- 422: Unprocessable Entity - Validation failed
- 429: Too Many Requests - Rate limit exceeded (400/min, 4000/hour)
- 500: Server Error - Internal server error
- 503: Service Unavailable - Server temporarily overloaded
- 504: Time Out - Response timeout

## Parameter Mapping

When reading documentation, map parameters to request:

**Path Parameters:**
```
API Path: /repos/:owner/:repo/branches
Actual Path: /repos/myuser/myrepo/branches
```

**Query Parameters:**
```
Documentation: page (integer) - Page number
Request: ?page=1&per_page=20
```

**Request Body:**
```
Documentation: name (string, required) - Repository name
Request Body: {"name": "my-new-repo"}
```

## INDEX.md File Format

### Global INDEX.md Structure

The global INDEX.md at `{project_path}/INDEX.md` should contain:

```markdown
# GitCode API Documentation Index

## Overview

- **Base URL**: https://api.gitcode.com/api/v5
- **Authentication**: access_token (query parameter or header)
- **Total APIs**: 154

## API Categories

| Category | Description | APIs Count | Documentation |
|----------|-------------|------------|---------------|
| Pull Requests | PR management | 44 | [PullRequests.md](PullRequests.md) |
| Repositories | Repository management | 36 | [Repositories.md](Repositories.md) |
| Issues | Issue tracking | 26 | [Issues.md](Issues.md) |
| Commit | Commit operations | 12 | [Commit.md](Commit.md) |
| Labels | Label management | 9 | [Labels.md](Labels.md) |
| Branch | Branch operations | 8 | [Branch.md](Branch.md) |
| Tag | Tag operations | 8 | [Tag.md](Tag.md) |
| Release | Release management | 8 | [Release.md](Release.md) |
| Search | Search operations | 3 | [Search.md](Search.md) |

## Quick Reference

### Most Used APIs

- [Create Repository](Repositories/create-file.md) - POST /repos/:owner/:repo/contents/:path
- [List Branches](Branch/get-branches.md) - GET /repos/:owner/:repo/branches
- [Create Issue](Issues/create-issue.md) - POST /repos/:owner/issues
- [Create Pull Request](PullRequests/create-pull-request.md) - POST /repos/:owner/:repo/pulls

## Statistics

- Total Categories: 9
- Total APIs: 154
- Last Updated: 2024-01-01
```

### Category INDEX.md Structure

The category INDEX.md at `{project_path}/{Category}/INDEX.md` should contain:

```markdown
# {Category} API Index

## Overview

- **Category**: {Category}
- **Base Path**: /repos/:owner/:repo (if applicable)
- **Total APIs**: {count}

## API List

| Index | API Name | Method | Path | Description | Documentation |
|-------|----------|--------|------|-------------|---------------|
| 1 | List Branches | GET | /repos/:owner/:repo/branches | List all branches | [get-branches.md](get-branches.md) |
| 2 | Create Branch | POST | /repos/:owner/:repo/branches | Create a new branch | [create-branch.md](create-branch.md) |
| 3 | Get Branch | GET | /repos/:owner/:repo/branches/:branch | Get branch details | [get-branch.md](get-branch.md) |
| 4 | Delete Branch | DELETE | /repos/:owner/:repo/branches/:name | Delete a branch | [delete-branch.md](delete-branch.md) |

## Quick Examples

### List Branches

```bash
curl "https://api.gitcode.com/api/v5/repos/owner/repo/branches?access_token=YOUR_TOKEN"
```

### Create Branch

```bash
curl -X POST "https://api.gitcode.com/api/v5/repos/owner/repo/branches?access_token=YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"refs": "master", "branch_name": "new-branch"}'
```

## Related Categories

- [Repositories](../Repositories.md) - Repository management
- [Pull Requests](../PullRequests.md) - Pull request operations
```

### INDEX.md Benefits

1. **Faster Lookup**: Direct access to API documentation without searching
2. **Better Organization**: Clear structure and categorization
3. **Quick Reference**: At-a-glance view of available APIs
4. **Navigation**: Easy links to detailed documentation
5. **Examples**: Quick copy-paste examples for common operations

## Workflow Example

### Example 1: Create a Repository

**User Request:** "Create a new GitCode repository named 'test-project'"

**Actions:**
1. **Try reading INDEX.md first:**
   - Check for `{project_path}/INDEX.md`
   - Check for `{project_path}/Repositories/INDEX.md`
   - If found, locate "create repository" API in the index
2. **Read API documentation:**
   - Read `Repositories/create-repo.md` (path from index or search)
3. Extract API details:
   - Method: POST
   - Path: /user/repos
   - Required: name
   - Optional: description, private, etc.
4. Validate parameters
5. Construct request:
   ```bash
   curl -X POST "https://api.gitcode.com/api/v5/user/repos?access_token=YOUR_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"name": "test-project"}'
   ```
6. Provide Python and cURL examples
7. Optionally execute and show response

### Example 2: List Repository Branches

**User Request:** "List all branches in owner/repo"

**Actions:**
1. **Try reading INDEX.md first:**
   - Check for `{project_path}/Branch.md`
   - If found, locate "list branches" API in the overview
2. **Read API documentation:**
   - Read `Branch/get-branches.md`
3. Extract API details:
   - Method: GET
   - Path: /repos/:owner/:repo/branches
4. Construct request:
   ```bash
   curl "https://api.gitcode.com/api/v5/repos/owner/repo/branches?access_token=YOUR_TOKEN"
   ```
5. Show response structure and example

### Example 3: Create an Issue

**User Request:** "Create an issue in myrepo with title 'Bug found'"

**Actions:**
1. **Try reading INDEX.md first:**
   - Check for `{project_path}/Issues.md`
   - If found, locate "create issue" API in the overview
2. **Read API documentation:**
   - Read `Issues/create-issue.md`
3. Extract required parameters: title, owner, repo
4. Construct request:
   ```bash
   curl -X POST "https://api.gitcode.com/api/v5/repos/owner/issues?access_token=YOUR_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"repo": "myrepo", "title": "Bug found"}'
   ```
5. Show response with issue number and URL

### Example 4: Using Global INDEX.md

**User Request:** "What APIs are available for managing repositories?"

**Actions:**
1. Read `{project_path}/INDEX.md`
2. Parse the index to find Repositories category
3. Read `{project_path}/Repositories.md`
4. Display all available repository APIs:
   - List repositories
   - Create repository
   - Get repository details
   - Update repository
   - Delete repository
   - etc.
5. Provide quick reference table from Repositories.md

## Quality Checklist

Before completing the task, verify:
- [ ] **Checked built-in documentation first (if applicable)**
- [ ] **Attempted to read INDEX.md files first (global and category-specific)**
- [ ] Correct API endpoint identified from documentation
- [ ] All required parameters are provided
- [ ] Parameter types are correct
- [ ] Authentication token is included
- [ ] Request format matches documentation
- [ ] Multiple language examples provided
- [ ] Response structure explained
- [ ] Error handling documented

## Tools Used

- **Read**: Read local API documentation files
- **SearchCodebase**: Search for relevant API documentation
- **Glob**: Find documentation files by pattern
- **WebFetch**: Execute API requests (if needed)
- **RunCommand**: Execute curl commands (if needed)
- **AskUserQuestion**: Ask for missing parameters or token

## Best Practices

- **Always try to read INDEX.md files first** before searching individual API files
- Always validate parameters before making requests
- Provide examples in multiple programming languages
- Explain response structure based on documentation
- Handle errors gracefully with helpful messages
- Respect API rate limits
- Cache documentation reads when possible
- Keep authentication tokens secure
- Use pagination for large result sets
- Follow GitCode API best practices
- Suggest creating INDEX.md files if they don't exist

## Common Mistakes to Avoid

1. **Not reading INDEX.md first**: Always check for INDEX.md files before searching
2. **Missing authentication**: Always include access_token
3. **Wrong parameter type**: Check documentation for types
4. **Missing required parameters**: Validate all required fields
5. **Incorrect URL encoding**: Encode special characters properly
6. **Ignoring pagination**: Handle large result sets with pagination
7. **Not handling errors**: Always check response status
8. **Hardcoding tokens**: Use environment variables instead
9. **Skipping documentation validation**: Always verify against docs
10. **Not suggesting INDEX.md creation**: If missing, suggest creating it

## Notes

- **Built-in documentation is always available** at `./references/`
- This skill includes complete GitCode API documentation (154 endpoints) out of the box
- **INDEX.md files are highly recommended** for faster API lookup and better organization
- Always verify the API base URL (GitCode may have different environments)
- Keep documentation updated with the latest API changes
- Consider implementing a cache for frequently used API endpoints
- No setup required - the skill works immediately with built-in docs