# 本地界面素材

所有素材由 `/assets` 提供；浏览器运行不请求 CDN、字体服务或图片服务。

- `daily-glow.webp`、`bamboo.webp`、`horse.webp`、`rooster.webp`、`solar-orb.webp`、`lunar-orb.webp`：本次根据用户参考图的风格，通过 Image Gen 生成；不是参考应用的素材拷贝。
- `icons/`：Phosphor Icons Core 2.1.1 的 regular 图标，MIT；保留原始 SVG，只选取页面实际使用的 13 个。包归档经过 npm SHA-512 integrity 校验，来源见 `icons/SOURCE.txt`，许可证见 `icons/LICENSE.txt`。
- `fonts/paper-serif.otf`：系统 Noto Serif CJK SC Regular 的字符子集，SIL Open Font License；来源 `/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc` 的 SC face。许可证及上游信息见 `fonts/LICENSE.txt`。动态中文缺字回退至设备宋体/衬线字体。
- `app.css`：页面布局与样式，无新增前端构建依赖。
