# Module Interaction Diagram

```
                         config.json
                             │
                             ▼
┌──────────┐          ┌──────────────┐
│  main.py │─────────▶│config_loader │
└────┬─────┘          └──────────────┘
     │                       │
     │                       ▼
     │                ┌──────────────┐
     │                │ custom_types │ (Config, Result, RawResult, ...)
     │                └──────┬───────┘
     │                       │ used by all modules
     ▼                       │
┌────────────────┐           │
│ solver_manager │◄──────────┘
└──┬──────────┬──┘
   │          │
   │          ├─────────────────────┐
   │          │                     ▼
   │          │              ┌─────────┐         ┌───────────────────┐
   │          │              │ factory │────────▶│ metadata_registry │
   │          │              └────┬────┘         │ (FORMAT_REGISTRY) │
   │          │                   │              └───────────────────┘
   │          │          creates + resolves parser
   │          │            ┌──────┴──────┐
   │ Phase 1  │ Phase 2    │             │
   ▼          ▼            ▼             ▼
┌─────────┐ ┌────────┐     ┌─────────────────┐
│converter│ │ runner │────▶│ parser_strategy  │
└────┬────┘ └───┬────┘     │ (ResultParser)   │
     │          │          └─────────────────┘
     │          │
     │ both use cmd_builder to resolve
     │ {input}, {output}, <, > tokens
     │ before calling generic_executor
     │          │
     ▼          ▼
┌──────────────────┐
│ generic_executor │ ◄── subprocess + psutil monitoring
└──────────────────┘

┌─────────┐
│ graph.py│ ◄── CSV/JSONL writers, JSON export, plot generation
└─────────┘
```

## Data Flow

1. `main.py` loads config via `config_loader`, then hands `Config` to `solver_manager`
2. `solver_manager` calls `factory` to create `Converter` and `Runner` instances
3. `factory` resolves format metadata and parsers from `metadata_registry` and `parser_strategy`, then creates and returns the configured `Converter` or `Runner`
4. Both `Converter` and `Runner` use `cmd_builder` to resolve option tokens, then delegate subprocess execution to `GenericExecutor`
6. `Runner` applies the injected `ResultParser` to map `RawResult` → `Result`
7. `graph.py` serializes results to CSV/JSONL/JSON and generates plots
