# 开发指南

中文 | [English](../en/development.md)

## 环境准备

```bash
git clone https://github.com/codeasier/gitcode-cli.git
cd gitcode-cli
pip install -e ".[dev]"
```

## 运行测试

完整执行：

```bash
conda run -n gitcode-cli python -m pytest tests
```

按层执行：

```bash
conda run -n gitcode-cli python -m pytest tests/unit/commands
conda run -n gitcode-cli python -m pytest tests/unit/adapters
conda run -n gitcode-cli python -m pytest tests/unit/services
conda run -n gitcode-cli python -m pytest tests/contracts
```

测试布局与设计意图见 [tests/README.md](../../tests/README.md)。

## 静态检查

```bash
python -m ruff check src/ tests/
python -m ruff format src/ tests/
python -m basedpyright src/
```
