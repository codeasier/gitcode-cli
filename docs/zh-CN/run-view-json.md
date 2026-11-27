# 读取一次工作流运行的元数据

`gc run view RUN -R OWNER/REPO --json workflowName,attempt,headSha,status` 只输出一个 JSON 对象。可任选字段，输出顺序与选择顺序一致：

| 字段 | 类型 | [GitCode v8 运行详情](https://docs.gitcode.com/docs/apis/get-api-v-8-repos-owner-repo-actions-runs-run-id/)字段 |
| --- | --- | --- |
| `attempt` | 整数 | 原样使用 `attempt`（包括 0） |
| `headSha` | 字符串 | `head_sha`，完整提交 SHA |
| `workflowName` | 字符串 | `workflow_name`，不是运行标题或 YAML 文件名 |
| `status` | 字符串 | GitCode 原生运行状态，不等同于 GitHub `conclusion` |

只读取一次当前运行详情，在同一份响应中检查运行 ID、完整 SHA 和 attempt。如须核对已知值，添加 `--attempt N --commit FULL_SHA`。身份不完整、与指定值不符或无法提供选中的工作流名称时，命令非零退出，标准输出为空。不会另外查询作业、工作流定义或日志。

字段名与 [gh run view](https://cli.github.com/manual/gh_run_view) 对应，但不支持历史 attempt 查询、其他 gh 输出字段或 gh 代理转发。原有作业、步骤和日志模式不变；这些模式的分页、排序选项不能与本次元数据选择合用。

也可显式选择 `status`。它是 GitCode 原生运行状态，不是 GitHub `conclusion`，不影响成功读取的退出码。选中该字段但数据缺失或无效时，命令报错，不输出 JSON。
