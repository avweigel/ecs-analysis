# ECS preservation — data to publish to S3

For the crop links on <https://avweigel.github.io/ecs-analysis/crops.html> to work off-VPN.

**Please put these in the bucket but don't make them live on OpenOrganelle** — we'd rather
they weren't listed on the portal, just reachable at the object store.

Same paths as NRS, `recon-1/em/<array>` and `recon-1/labels/groundtruth/<crop>`. The site
only reads `all` from each crop.

## Needed

| dataset | image | crops |
| :-- | :-- | :-- |
| `jrc_mus-cortex-2` | `em/fibsem-uint16` | `crop1116` |
| `jrc_mus-cortex-3` | ok | `crop1033` `crop1034` `crop1035` `crop1036` `crop1037` `crop1045` `crop1046` |
| `jrc_mus-cortex-4` | `em/fibsem-uint16` | `crop1140` `crop1141` `crop1142` `crop1143` |
| `jrc_mus-heart-4` | `em/fibsem-uint16` | `crop1149` `crop1150` `crop1151` `crop1152` |
| `jrc_mus-heart-6` | `em/fibsem-uint16` | `crop1145` `crop1146` `crop1147` `crop1148` |
| `jrc_mus-kidney` | ok | ok |
| `jrc_mus-kidney-4` | `em/fibsem-uint16` | `crop1134` `crop1135` `crop1136` `crop1137` `crop1138` `crop1144` |
| `jrc_mus-liver` | ok | `crop1038` `crop1039` `crop1040` `crop1041` `crop1042` `crop1043` `crop1044` `crop1118` `crop1119` `crop1120` `crop1121` `crop1122` |
| `jrc_mus-liver-8` | `em/fibsem-uint16` | `crop1071` `crop1072` `crop1073` `crop1074` `crop1075` `crop1123` `crop1124` `crop1125` `crop1126` `crop1127` |

6 image volumes, 48 crop groups.

## Flat list

```
jrc_mus-cortex-2/jrc_mus-cortex-2.zarr/recon-1/labels/groundtruth/crop1116
jrc_mus-cortex-3/jrc_mus-cortex-3.zarr/recon-1/labels/groundtruth/crop1033
jrc_mus-cortex-3/jrc_mus-cortex-3.zarr/recon-1/labels/groundtruth/crop1034
jrc_mus-cortex-3/jrc_mus-cortex-3.zarr/recon-1/labels/groundtruth/crop1035
jrc_mus-cortex-3/jrc_mus-cortex-3.zarr/recon-1/labels/groundtruth/crop1036
jrc_mus-cortex-3/jrc_mus-cortex-3.zarr/recon-1/labels/groundtruth/crop1037
jrc_mus-cortex-3/jrc_mus-cortex-3.zarr/recon-1/labels/groundtruth/crop1045
jrc_mus-cortex-3/jrc_mus-cortex-3.zarr/recon-1/labels/groundtruth/crop1046
jrc_mus-cortex-4/jrc_mus-cortex-4.zarr/recon-1/labels/groundtruth/crop1140
jrc_mus-cortex-4/jrc_mus-cortex-4.zarr/recon-1/labels/groundtruth/crop1141
jrc_mus-cortex-4/jrc_mus-cortex-4.zarr/recon-1/labels/groundtruth/crop1142
jrc_mus-cortex-4/jrc_mus-cortex-4.zarr/recon-1/labels/groundtruth/crop1143
jrc_mus-heart-4/jrc_mus-heart-4.zarr/recon-1/labels/groundtruth/crop1149
jrc_mus-heart-4/jrc_mus-heart-4.zarr/recon-1/labels/groundtruth/crop1150
jrc_mus-heart-4/jrc_mus-heart-4.zarr/recon-1/labels/groundtruth/crop1151
jrc_mus-heart-4/jrc_mus-heart-4.zarr/recon-1/labels/groundtruth/crop1152
jrc_mus-heart-6/jrc_mus-heart-6.zarr/recon-1/labels/groundtruth/crop1145
jrc_mus-heart-6/jrc_mus-heart-6.zarr/recon-1/labels/groundtruth/crop1146
jrc_mus-heart-6/jrc_mus-heart-6.zarr/recon-1/labels/groundtruth/crop1147
jrc_mus-heart-6/jrc_mus-heart-6.zarr/recon-1/labels/groundtruth/crop1148
jrc_mus-kidney-4/jrc_mus-kidney-4.zarr/recon-1/labels/groundtruth/crop1134
jrc_mus-kidney-4/jrc_mus-kidney-4.zarr/recon-1/labels/groundtruth/crop1135
jrc_mus-kidney-4/jrc_mus-kidney-4.zarr/recon-1/labels/groundtruth/crop1136
jrc_mus-kidney-4/jrc_mus-kidney-4.zarr/recon-1/labels/groundtruth/crop1137
jrc_mus-kidney-4/jrc_mus-kidney-4.zarr/recon-1/labels/groundtruth/crop1138
jrc_mus-kidney-4/jrc_mus-kidney-4.zarr/recon-1/labels/groundtruth/crop1144
jrc_mus-liver/jrc_mus-liver.zarr/recon-1/labels/groundtruth/crop1038
jrc_mus-liver/jrc_mus-liver.zarr/recon-1/labels/groundtruth/crop1039
jrc_mus-liver/jrc_mus-liver.zarr/recon-1/labels/groundtruth/crop1040
jrc_mus-liver/jrc_mus-liver.zarr/recon-1/labels/groundtruth/crop1041
jrc_mus-liver/jrc_mus-liver.zarr/recon-1/labels/groundtruth/crop1042
jrc_mus-liver/jrc_mus-liver.zarr/recon-1/labels/groundtruth/crop1043
jrc_mus-liver/jrc_mus-liver.zarr/recon-1/labels/groundtruth/crop1044
jrc_mus-liver/jrc_mus-liver.zarr/recon-1/labels/groundtruth/crop1118
jrc_mus-liver/jrc_mus-liver.zarr/recon-1/labels/groundtruth/crop1119
jrc_mus-liver/jrc_mus-liver.zarr/recon-1/labels/groundtruth/crop1120
jrc_mus-liver/jrc_mus-liver.zarr/recon-1/labels/groundtruth/crop1121
jrc_mus-liver/jrc_mus-liver.zarr/recon-1/labels/groundtruth/crop1122
jrc_mus-liver-8/jrc_mus-liver-8.zarr/recon-1/labels/groundtruth/crop1071
jrc_mus-liver-8/jrc_mus-liver-8.zarr/recon-1/labels/groundtruth/crop1072
jrc_mus-liver-8/jrc_mus-liver-8.zarr/recon-1/labels/groundtruth/crop1073
jrc_mus-liver-8/jrc_mus-liver-8.zarr/recon-1/labels/groundtruth/crop1074
jrc_mus-liver-8/jrc_mus-liver-8.zarr/recon-1/labels/groundtruth/crop1075
jrc_mus-liver-8/jrc_mus-liver-8.zarr/recon-1/labels/groundtruth/crop1123
jrc_mus-liver-8/jrc_mus-liver-8.zarr/recon-1/labels/groundtruth/crop1124
jrc_mus-liver-8/jrc_mus-liver-8.zarr/recon-1/labels/groundtruth/crop1125
jrc_mus-liver-8/jrc_mus-liver-8.zarr/recon-1/labels/groundtruth/crop1126
jrc_mus-liver-8/jrc_mus-liver-8.zarr/recon-1/labels/groundtruth/crop1127
```

Bucket needs public read + CORS. Whatever bucket you use, tell me and I'll point the site at
it — it's one constant (`PUBLIC_S3_BASE` in `scripts/build_neuroglancer.py`).

`python scripts/build_neuroglancer.py --probe` re-checks the bucket and updates the site's
per-dataset status, so run it after a batch and the links switch over on their own.
