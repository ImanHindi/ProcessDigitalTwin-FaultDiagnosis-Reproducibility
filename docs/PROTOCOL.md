# Final19 scientific protocol

| Item | Frozen setting |
|---|---|
| Physical process | One-tank Jameed heating/mixing, product transfer, CIP |
| Accepted physical model | v4.6.2 |
| Scientific campaign layer | v4.6.3 |
| Class count | 19 = normal (1) + process/actuator (12) + sensor (6) |
| Independent simulations | 1,900; 100/class |
| Simulation duration | 9,000 s/run |
| Export frequency | 1 Hz |
| Windowing | Non-overlapping 60 s windows |
| Features | 17 channels × 10 statistics = 170 |
| Partition unit | Independent run ID, **not** a window |
| Fixed partition | 70 train / 15 validation / 15 test runs per class |
| Partition totals | 1,330 / 285 / 285 runs |
| Nominal data gates | 38-run smoke → 190-run development → 1,900 scientific |
| Fine-grained supervised inclusion | Dedicated normal or active-fault window (≥50% active) |
| Healthy-only anomaly modelling | Fit representation on healthy training data; validation-set threshold/selection |
| Model selection | Training and validation only; locked test never used for tuning |

## Fault-code dictionary

| Code | Fault class |
|---|---|
| 0 | Normal |
| 1 | Production fill-pump degradation |
| 2 | CIP supply-pump degradation |
| 3 | Production inlet-valve blockage |
| 4 | Tank inlet-valve blockage |
| 5 | Product discharge-valve blockage |
| 6 | Product discharge-valve leakage / stuck open |
| 7 | Heating degradation |
| 8 | Agitator degradation |
| 9 | CIP inlet-valve blockage |
| 10 | CIP return-valve blockage |
| 11 | Product discharge-pump degradation |
| 12 | CIP return-pump degradation |
| 101 | Temperature-sensor bias |
| 102 | Level-sensor bias |
| 103 | Production-flow sensor scale error |
| 104 | Pressure-sensor drift |
| 105 | RPM-sensor excessive noise |
| 106 | Temperature-sensor dropout |

## Window features

`ml/config.json` lists the exact 17 channels. `ml/features.py` performs derivative enrichment, causal labeling and 10 summary statistics: mean, standard deviation, minimum, maximum, median, fifth percentile, 95th percentile, final sample, linear slope and root mean square (RMS).

The study's synthetic campaign is neither measured factory telemetry nor independent evidence of industrial prognosis. First-correct diagnosis after fault onset is a *diagnostic delay*, not predictive lead time.
