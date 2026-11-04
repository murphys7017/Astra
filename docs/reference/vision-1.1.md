# Astra：统一设计思想、参考项目与工程控制基线

**文档性质**：项目设计思想与工程控制基线  
**版本**：Vision 1.1（2026-11-03）  
**适用范围**：全新独立项目 Astra，以 Python 为首选实现语言

本文用于明确项目思想、核心概念、组件协作方式、参考项目和工程实施原则。设计原则与具体实现细节应当区分：前者构成项目的长期方向，后者通过实际开发和测试逐步确定。

---

## 一、项目定义与核心思想

**Astra 是一个让开发者自由组织智能系统的可组合组件运行时，而不是一套预先规定聊天或 Agent 执行流程的框架。**

Astra 的核心目标，是让开发者根据自身需求，选择不同组件、组合不同工作流，并通过统一的能力调用、流式交互、路由与事件机制，让这些工作流共同构成一个完整系统。

系统中的模型、记忆、工具、Agent、工作流、输入输出设备和身体运行时，都能够通过统一的组件机制接入。

Astra 本身不规定一个智能系统必须具有哪些能力，也不规定这些能力必须按照什么顺序运行。

### 核心原则

1. **Component 是基本的装载和生命周期单位。** 模型、工具、Agent Loop、Router、Workflow、平台适配器和设备系统，都可以作为 Component。
2. **Capability 是组件之间的稳定契约。** 使用方依赖能力，而不是依赖具体组件实现。
3. **Composition 决定系统行为。** 开发者可以自行组织工作流，并决定组件之间的调用顺序、条件、并发和数据传递关系。
4. **Workflow 可以成为 Component。** 工作流能够组合其他能力，也能够对外提供自己的能力，供其他工作流调用。
5. **Microkernel 负责通用运行机制。** 组件注册、依赖解析、调用关系、生命周期、取消、资源管理和诊断由内核负责。
6. **本地与远程遵循相同的能力语义。** 组件可以在本地运行，也可以在未来通过 HTTP、WebSocket、IPC 等方式接入。
7. **工程控制服务于系统可靠性。** 通过明确的依赖、资源所有权、验证与反馈机制，控制架构复杂度。

**一句话概括：能力由组件提供，行为由组合定义，执行由运行时保障，业务复杂度留在业务组件内部。**

---

## 二、项目背景与需求来源

Astra 的设计并不是从抽象框架开始，而是源于 AG99、AG99live 等实际项目的开发经验。

### 2.1 AstrBot

参考项目：

https://github.com/AstrBotDevs/AstrBot

AstrBot 提供了相对完整的机器人基础设施，包括平台接入、消息处理、LLM Provider、插件、Agent、工具、会话和管理界面。

这些能力对 Astra 具有参考价值，但 Astra 不应直接继承 AstrBot 的核心运行架构。

AstrBot 可以作为功能需求和兼容生态的参考。

### 2.2 AG99

项目地址：

https://github.com/murphys7017/AG99

当前规范仓库路径：

https://github.com/murphys7017/AstrBot

AG99 基于 AstrBot 独立演进，逐渐形成了以持续 Persona 为中心的智能体主应用。

它包含以下重要能力和设计经验：

- 持续存在的 Persona 与 Personal Runtime；
- 普通对话和复杂任务的分层；
- ContextPack、Structured Prompt 和目标上下文投影；
- Memory、Knowledge、Tool、Skill、Agent 和 Executor；
- Core Router、Planner 与任务执行；
- Core 执行结果向 Persona Expression 回流；
- Observation、Gate、Policy、ActionIntent 组成的主动行为机制；
- 流式表达、统一输出与结果投递；
- 会话状态、执行状态和生命周期管理。

AG99 证明，一个完整的智能主体不仅需要模型和工具，还需要上下文组织、状态管理、行为决策和统一表达。

这些是 Astra 上层组件与工作流的重要需求来源。

### 2.3 AG99live

项目地址：

https://github.com/murphys7017/AG99live

AG99live 是 AG99 的桌面身体运行时。

其重要能力包括：

- 桌面输入、麦克风与 STT；
- 流式语音识别和文本输入；
- TTS 与音频播放；
- Persona 分段输出；
- Motion Provider 与语义动作；
- PlaybackTimeline；
- ModelEngine；
- Live2D 参数编译、融合和渲染；
- 用户打断、动作抢占和迟到结果处理；
- 桌面观察和主动互动；
- Spout、OBS、ESP32、Bilibili 等输入输出能力。

AG99live 的经验说明，实时音频、动作和身体表现具有明确的时间、身份及资源所有权要求。

这些领域规则不应全部上升为 Astra 内核规则。

Astra 需要提供可靠的组件调用和生命周期机制，而 AG99live 继续负责专业的身体表现逻辑。

### 2.4 Astra 的定位

Astra 是独立运行底座。

AG99 可以成为基于 Astra 构建的 Persona-first 智能应用。

AG99live 可以成为基于 Astra Capability 接入的身体运行时。

其他系统也可以采用完全不同的能力组合，例如：

- 独立任务 Agent；
- 无界面的自动化系统；
- 语音交互程序；
- 多 Agent 系统；
- 远程 GPU 推理系统；
- Android 设备控制系统；
- 不使用 LLM 的规则和工具系统。

Astra 的价值在于能够支持这些不同的组织方式，而不要求每一种应用重新编写底层组件运行机制。

---

## 三、核心概念

### 3.1 Component

Component 是 Astra 的基本装载、扩展和生命周期单位。

它表示一个能够独立提供能力、声明依赖并接受 Runtime 管理的功能实体。

一个 Component 应能够描述：

- 身份和版本；
- 配置；
- 提供的 Capability；
- 依赖的 Capability；
- 运行作用域；
- 权限与资源要求；
- 启动、停止和释放行为。

Component 可以同时提供多项 Capability。

例如：

**MiniMaxComponent**

- `llm.generate`
- `llm.stream`

**MemoryComponent**

- `memory.search`
- `memory.write`

**AndroidComponent**

- `android.tap`
- `android.swipe`
- `android.screenshot`
- `device.observe`

**AG99liveComponent**

- `avatar.express`
- `audio.play`
- `desktop.observe`

Component 不应该被设计成庞大的继承体系。

Provider、Tool、Executor、Adapter、Agent 和 Router 都是组件可能承担的角色。

| 传统概念 | Astra 中的含义 |
|---|---|
| Provider | 某项 Capability 的提供者 |
| Tool | 向 Agent 或 Workflow 暴露的可调用能力 |
| Executor | 提供执行能力或外部副作用能力的组件 |
| Adapter | 连接外部平台、协议或设备的组件 |
| Agent / Agent Loop | 提供智能执行策略或循环的组件 |
| Router / Policy | 提供路由决策或策略判断的组件 |
| Workflow | 组合其他能力并能够对外提供能力的组件 |

组件化的重点不是把所有函数变成插件，而是让**需要独立装载、替换、组合和管理生命周期的功能**具备统一的接入方式。

领域组件内部可以继续保留自己的算法、对象和运行结构。

### 3.2 Capability

Capability 描述组件能够提供什么能力，以及其他组件应当如何使用该能力。

它是组件之间稳定的交互契约。

Capability 应能够明确：

- 能力标识；
- 契约版本；
- 输入类型；
- 输出类型；
- 交互模式；
- 错误与终态；
- 超时和取消；
- 流式处理及背压；
- 权限要求；
- 副作用性质。

示例：

`llm.generate`

输入：模型请求与上下文。  
输出：模型结果或文本流。  
交互模式：Invoke / Stream。  
取消：支持。

`file.write`

输入：文件写入请求。  
输出：写入结果。  
交互模式：Invoke。  
副作用：修改外部文件。  
权限：文件写入权限。

`avatar.express`

输入：结构化表现请求。  
输出：表现受理、状态或完成结果。  
交互模式：Invoke / Stream。  
执行细节：由身体组件管理。

这些名称是概念示例，具体 API 命名由工程验证确定。

### 3.3 Provider、Tool 与 Capability 的关系

Provider 不再是一套独立于 Component 的基础类型。

某个 Component 提供一项 Capability，它就可以成为该 Capability 的 Provider。

Tool 同样不是必须与 Component 平级的实体。

例如，FileSystemComponent 可以提供 `file.read` 和 `file.write`。当 Agent 被授权使用这些能力时，它们可以以 Tool 的形式暴露给模型。

Capability 的存在、是否允许被 Agent 调用、以及 Agent 如何描述工具 Schema，是三个相关但不同的问题。

### 3.4 Microkernel

Astra Microkernel 是整个系统最小、稳定的运行基础。

其主要职责包括：

- Component 注册与管理；
- Capability Registry；
- Capability Resolution；
- Invocation；
- Run 与因果身份；
- Scope；
- Lifecycle；
- Cancellation；
- 资源所有权与释放；
- 权限执行边界；
- 基础诊断与 Trace。

Microkernel 不负责具体智能业务。

它不需要知道 Persona、LLM、STT、TTS、Live2D、Memory 或 Agent Loop 的内部含义。

这些能力由组件提供，并通过组合机制形成实际应用。

### 3.5 Composition

Composition 表示组件和能力之间的组合关系。

它描述：

- 哪些能力参与执行；
- 以什么顺序调用；
- 是否并发；
- 根据什么条件选择分支；
- 数据如何传递；
- 结果如何返回；
- 失败时如何处理；
- 子任务与父任务之间具有怎样的生命周期关系。

Composition 是 Astra 实现自由组合的重要概念。

### 3.6 Workflow

Workflow 是一种可执行的能力组合。

它能够调用其他 Component 或 Workflow，并可以对外提供自己的 Capability。

例如：

**ConversationWorkflow**

提供 `conversation.respond`。

内部可能调用：

- Context；
- Memory；
- LLM；
- Persona；
- Output。

**TaskWorkflow**

提供 `task.execute`。

内部可能调用：

- Router；
- Planner；
- Agent；
- Tool；
- Executor。

**AvatarWorkflow**

提供 `avatar.express`。

内部可能组织：

- TTS；
- Motion；
- Playback；
- Avatar。

Workflow 内部可以复杂，但对外仍然遵循统一 Capability 契约。

需要区分三个概念：

- **Workflow Definition**：工作流的组合定义。
- **Workflow Run**：工作流的一次实际执行。
- **Workflow Component**：对外提供可调用工作流能力的组件。

第一阶段可使用 Python 定义和编排工作流。

未来可以根据实际需要设计 Workflow IR、DSL、JSON、XML 或图形编辑器。

### 3.7 Profile / Application

Profile 或 Application 表示一种具体的组件组合和能力绑定方式。

例如：

**AG99 Application**

- Persona；
- Memory；
- Conversation；
- Router；
- Agent；
- Policy。

**AG99live Application**

- AG99 能力；
- Desktop Input；
- STT；
- TTS；
- Motion；
- Avatar。

**Headless Application**

- Agent；
- Memory；
- Tool；
- Task Workflow。

不同 Application 可以使用相同的 Astra Runtime，但选择不同的组件与流程。

组件的安装、可用、激活和实际被选中调用应当具有明确区别。

---

## 四、组件交互与工作流协作

用户能够自主创建工作流，并让工作流相互调用和协作，是 Astra 的核心能力。

Astra 应明确区分以下交互语义：

| 机制 | 职责 |
|---|---|
| Resolve | 找到满足要求的 Capability 提供者 |
| Invoke | 显式调用能力并获得结果 |
| Stream | 有序传递连续数据 |
| Contribute | 补充结构化上下文或事实 |
| Route | 决定后续执行路径 |
| Event | 发布已发生的事实 |
| Control | 改变执行状态 |

这些是交互语义，不代表必须实现七套独立总线。

### 4.1 Resolve

Resolve 负责根据 Capability、Scope 和约束找到可用组件。

调用方只依赖能力契约，不依赖具体组件实现。

例如一个工作流需要 `llm.generate`，Runtime 可以根据当前绑定找到 MiniMax、本地模型或其他实现。

### 4.2 Invoke

Invoke 表示一次明确的能力调用。

例如：

ConversationWorkflow 调用 KnowledgeComponent 检索知识，再调用 AgentWorkflow 执行任务。

调用之间应有明确的请求、结果、错误和因果身份。

### 4.3 Stream

Stream 用于连续、有顺序的增量数据。

典型场景：

- 麦克风音频流；
- STT 增量结果；
- LLM 流式输出；
- TTS 音频流；
- Agent 执行进度。

Stream 需要明确：

- 数据顺序；
- 正常结束；
- 错误结束；
- 取消；
- 背压；
- 资源释放。

不应默认用 EventBus 广播每个音频分块或 Token。

### 4.4 Contribute

Contribute 表示向工作流提供结构化上下文或事实。

例如：

- Memory；
- Knowledge；
- Persona；
- Emotion；
- Environment。

这些组件提供材料，而不是直接决定最终 Prompt 或任意修改全局状态。

由具体工作流负责收集、选择和组织上下文。

Contribute 可以通过 Invoke 或其他合适的机制实现，不要求在内核中创建独立消息总线。

### 4.5 Router

Router 负责根据输入和上下文决定下一步的执行路径。

例如：

InputWorkflow 调用 Router，获得以下决策之一：

- Conversation；
- Task；
- Ignore；
- Human Approval。

随后由当前工作流执行相应调用。

Router 不直接授予工具权限，也不必须承担任务执行和输出管理职责。

### 4.6 EventBus

EventBus 用于事实通知和松耦合协作。

例如：

DesktopObserver 发布 `desktop.user_returned`。

ProactiveWorkflow 订阅该事件，根据自己的 Gate 和 Policy 决定是否启动 ConversationWorkflow。

事件表示已经发生的事实，不等于要求所有订阅者立即执行某个动作。

订阅者如果创建新的工作流执行，应具有自己的 Run、Scope、权限和因果关联。

事件订阅由所属 Component 或 Scope 管理，并在停止时释放。

事件持久化、可靠投递和重放等能力需要通过独立设计确定，不应默认认为简单的内存事件机制已经具备这些性质。

### 4.7 Control

Control 用于管理正在进行的执行。

例如：

- Cancel；
- Stop；
- Pause；
- Resume；
- Retry；
- Approval。

不同 Control 应具有清晰的受理与结果语义。

暂停、恢复和重试不一定适用于所有 Capability，应根据具体能力契约确定。

---

## 五、多工作流组合示例

一套基于 Astra 的智能交互应用可以组织为：

```text
User / Microphone / QQ / Bilibili
                 |
          Source Components
                 |
           InputWorkflow
                 |
          Router Component
          /      |       \
         /       |        \
Conversation    Task    Proactive
 Workflow     Workflow    Workflow
         \      |       /
          \     |      /
          Persona / Expression
                 |
        Text / Speech / Motion
                 |
         AG99live Body Runtime
```

另一种应用也可以不需要 Persona 或身体表现。

例如：

```text
Scheduled Event
      |
TaskWorkflow
      |
Planner
      |
Tools / Executors
      |
Result
      |
RecordWorkflow
```

工作流结构由开发者决定。

Astra 不需要为每一种流程重新实现底层运行机制。

### 工作流之间的生命周期关系

当 Workflow A 调用 Workflow B 时，应当明确：

- B 是否属于 A 的子执行；
- A 取消时 B 是否取消；
- B 的错误是否传播到 A；
- B 是否允许转为长期后台执行；
- 谁拥有 B 的资源；
- 如何处理迟到结果。

子调用默认归属父级 Scope。

长期后台执行应显式移交到合适的长期 Scope，并保留因果关系。

跨工作流重试不得默认重放已经产生外部副作用的操作。

---

## 六、数据与消息规范

Astra 应先统一语义，再决定具体传输格式。

本地 Python Component 之间可以直接传递明确的类型化数据。

跨进程或跨语言时，再通过序列化与传输层映射相同的能力契约。

### 6.1 基础数据结构

第一阶段可考虑以下概念：

| 结构 | 含义 |
|---|---|
| Content / ContentPart | 文本、音频、图片、结构化数据或资源引用 |
| CapabilityRequest | 能力调用请求 |
| InvocationResult | 调用结果、错误及终态 |
| StreamItem / StreamEnd | 流式数据及结束状态 |
| ContextContribution | 上下文贡献 |
| DomainEvent | 已发生的领域事实 |
| ControlRequest | 执行控制请求 |

这些是概念级结构，实际 DTO 应由验证用例决定。

### 6.2 通用身份与领域身份

Astra 负责维护通用的执行因果关系。

例如：

- run_id；
- invocation_id；
- parent_id；
- correlation_id。

AG99、AG99live 等领域组件仍然可以维护：

- turn_id；
- message_id；
- segment_id；
- tts_request_id；
- task_id；
- motion_run_id。

Astra 不应为了统一身份而把 Live2D 的 Segment 逻辑直接写入 Microkernel。

### 6.3 Context

Context 表示某次执行能够访问的受限运行环境。

它可以包含：

- 当前 Scope；
- 当前权限；
- Capability 解析入口；
- 必要的执行身份；
- Trace 信息；
- 显式提供的领域事实。

Context 不应成为所有组件共享并任意修改的全局字典。

Memory、Persona、Knowledge、Emotion 等上下文应通过清晰的贡献契约交付，由消费方决定使用范围与可见性。

### 6.4 传输边界

同进程：

直接使用类型化对象。

跨进程或远程：

采用具有明确类型、版本、关联身份和 Payload 的传输 Envelope。

**能力契约是共同边界，具体消息格式只是它的传输实现。**

---

## 七、依赖、作用域与生命周期

这部分主要吸收 Cordis 的空间与时间可组合性思想。

### 7.1 显式依赖

组件通过 `provides` 和 `requires` 声明能力关系。

Runtime 在具体 Scope 中解析依赖。

同一个 Capability 可以由不同 Component 提供，不同应用或会话也可以使用不同的能力绑定。

不应要求组件通过隐藏全局单例或直接导入其他组件的内部实现建立长期强依赖。

### 7.2 Scope

建议的概念结构：

```text
Runtime Scope
    |
Application / Session Scope
    |
Workflow / Interaction Run Scope
    |
Invocation Scope
```

这是作用域的语义关系，不要求所有应用必须具有完整四级结构。

例如不涉及聊天的自动化程序可以没有 Session。

Scope 主要用于确定：

- 资源归属；
- 任务生命周期；
- 订阅归属；
- 权限和可见范围；
- 取消传播；
- 清理行为。

### 7.3 生命周期

Component 应具备清晰的启动、停止和释放语义。

Component 注册的运行时资源应当能够被统一管理，例如：

- Capability 注册；
- EventBus 订阅；
- 后台任务；
- 网络连接；
- 临时文件；
- 设备监听；
- 流式数据资源。

Component 或 Scope 停止时，应按规则清理相关资源。

### 7.4 可逆副作用

需要区分两种副作用。

**运行时注册副作用**：例如注册服务、订阅事件、启动后台任务，应该能够在生命周期结束时清理。

**外部业务副作用**：例如写文件、发送消息、执行 Shell、控制设备，并不因为组件停止而自动撤销。

外部业务副作用需要明确权限、执行回执、幂等和必要的补偿策略。

### 7.5 取消与终态

Invocation 和 Workflow Run 应当具有清晰、统一的执行状态来源。

需要区分：

- 正常完成；
- 失败；
- 取消；
- 超时；
- 资源清理完成。

同时应区分不同领域的完成事实。

例如：

- 工具调用成功；
- 消息发送成功；
- 用户端播放完成。

这些不是同一件事。

---

## 八、本地与远程 Component

Astra 首选 Python 实现，并优先验证单进程本地执行。

但 Component 的能力契约不应依赖部署位置。

未来可支持：

```text
Workflow
   |
Capability
   |
Binding / Transport
   |
   +-- Local Python
   +-- Process / IPC
   +-- HTTP
   +-- WebSocket
   +-- Native Component Host
   +-- Android Component Host
```

例如同一 `motion.generate` 能力，可以先由本地 Python Component 实现，之后替换为远程 GPU Component。

上层工作流仍然依赖相同的 Capability。

远程组件设计应考虑：

- 能力与协议版本；
- 请求身份；
- 超时；
- 取消；
- 鉴权；
- 健康状态；
- 断线；
- 流式传输；
- 资源引用。

第一阶段不需要实现完整的远程组件部署、服务发现或分布式调度。

当前工程只需保证公共能力契约具有清晰语义，并允许未来建立远程传输映射。

---

## 九、AG99、AG99live 与 Astra 的关系

### 9.1 AG99：智能主体应用

AG99 可以基于 Astra 组织：

- Persona Component；
- Personal Runtime；
- Memory；
- Knowledge；
- Context Contributors；
- Router；
- Planner；
- Agent Loop；
- Policy；
- Expression；
- Conversation Workflow；
- Task Workflow。

AG99 最重要的领域原则之一，是统一管理用户可见的 Persona 表达。

Astra 并不要求其他应用遵循相同的 Persona 规则。

### 9.2 AG99live：身体运行时

AG99live 可以通过 Capability 接入 Astra。

对外提供适当的身体与设备能力，例如：

- `avatar.express`；
- `audio.play`；
- `desktop.observe`；
- `device.output`。

其内部继续保留：

- PlaybackTimeline；
- TurnPlaybackSessionStore；
- ModelEngine；
- ActiveParameterMixer；
- Live2D Runtime；
- 音频与设备管理。

Astra 不应接管 Live2D 逐帧计算，不应复制 AG99live 的播放时钟。

`output.segment.v6`、`engine.motion_intent.v4` 和 `engine.parameter_plan.v3` 等仍属于身体领域协议。

### 9.3 NeuroBrain：可选状态能力

项目地址：

https://github.com/murphys7017/NeuroBrain

NeuroBrain 可以作为持续状态、情绪或心理状态领域的能力提供者。

例如提供当前状态查询或上下文贡献。

它不应成为 Astra Microkernel 的基础依赖。

### 9.4 AstrBot 兼容

AstrBot 的平台、插件、Provider 和 Tool 生态可以作为未来兼容参考。

如果确有需要，可以开发独立的 AstrBot Compatibility Adapter。

兼容层不应改变 Astra 的基础 Component/Capability 契约。

---

## 十、重要参考项目与设计借鉴

### 10.1 Cordis

仓库：

https://github.com/cordiverse/cordis

论文：

https://arxiv.org/abs/2608.25512

论文相关仓库：

https://github.com/cordiverse/paper

**主要借鉴：**

空间可组合性：

- 显式依赖；
- 能力解析；
- Scope；
- 动态组合。

时间可组合性：

- 生命周期；
- 资源所有权；
- 可逆注册；
- 副作用清理。

Astra 应吸收这些机制所解决的问题，并使用适合 Python 的接口重新实现。

### 10.2 DeepSeek Harness

官方仓库：

https://github.com/deepseek-ai/deepseek-harness

Everything is Plugin：

https://dshx.dev/docs/introduction/everything-is-plugin/

Profile / Bundle 参考：

https://dshx.dev/docs/quickstart/profiles/

**主要借鉴：**

- 一切可替换的系统行为都可以组件化；
- Agent Loop 可以成为插件；
- Tool Service 和 Session 等基础服务可以替换；
- 不同 Application 可以通过不同组件组合形成；
- 不必把 Agent 流程固定写在内核中。

Astra 应进一步支持工作流自由组织，并通过 Capability、Router、EventBus 等建立明确的跨流程协作。

具体插件 API 与配置方式应以 Astra 的实现验证为准。

### 10.3 Vibe Engineering Cybernetics

项目地址：

https://github.com/murphys7017/VibeEngineeringCybernetics

Agent 工程规则：

https://github.com/murphys7017/VibeEngineeringCybernetics/blob/master/AGENTS.md

AI 运行指南：

https://github.com/murphys7017/VibeEngineeringCybernetics/blob/master/.ai/index.md

**主要借鉴：**

- 根据任务性质和风险选择工程控制强度；
- 修改前检查相关代码和架构约束；
- 尽可能保持变更范围最小；
- 验证实际行为；
- 明确记录未验证的内容；
- 通过反馈和纠正实现工程闭环。

这一项目主要用于 Astra 的开发治理，而不是作为 Component Runtime 的代码基础。

### 10.4 参考项目职责汇总

| 项目 | 在 Astra 中的主要参考价值 |
|---|---|
| AstrBot | 平台、Provider、插件和 Agent 能力清单 |
| AG99 | Persona、上下文、智能执行和主动行为 |
| AG99live | 实时输入输出、动作、播放时间线和设备 |
| NeuroBrain | 持续状态和情绪领域能力 |
| Cordis | 组件依赖、作用域、生命周期与副作用清理 |
| DeepSeek Harness | Agent Loop 可替换、组件化应用组合 |
| Vibe Engineering Cybernetics | 工程控制、风险管理与验证闭环 |

这些项目是需求与设计参考，不是 Astra 的必需运行依赖。

---

## 十一、工程控制原则

Astra 的工程目标不只是实现组件扩展，还要保证长期演进时不会不断增加难以维护的隐式复杂度。

### 11.1 开发闭环

开发工作遵循：

```text
明确目标
   |
检查现有设计和代码
   |
评估变更风险
   |
实施最小必要修改
   |
验证行为
   |
修正问题或报告限制
```

风险较高的工作，例如修改 Component、Capability、Invocation、Scope 和 Stream 公共契约，需要更严格的设计检查和测试。

局部低风险修改不需要引入额外的复杂审批和文档流程。

### 11.2 架构边界

应重点检查：

- 组件之间是否依赖内部实现；
- Capability 是否具有明确输入输出；
- 同一执行状态是否存在多个写入 Owner；
- EventBus 是否隐藏了必要的业务调用关系；
- Router 是否混合权限、执行和输出职责；
- 后台任务与订阅是否能够释放；
- 取消是否正确传播；
- 有副作用的操作是否被不安全地重试；
- 是否为了未来扩展引入当前不必要的抽象；
- 是否通过宽松 fallback 掩盖真实错误。

### 11.3 公共抽象的引入标准

每增加一个公共抽象，应该明确：

1. 它解决什么实际问题或必须保证什么不变量？
2. 现有机制为什么无法满足？
3. 会增加什么状态、依赖和生命周期责任？
4. 如何通过测试验证？
5. 后续修改或删除它会影响哪些组件？

公共抽象应当以实际必要性和验证结果为依据。

### 11.4 状态管理

只有会影响执行、恢复、决策或诊断的状态，才需要成为正式管理对象。

不应为了记录而不断创建新的状态、快照或 Ledger。

同一事实应尽量具有唯一权威来源。

### 11.5 验证标准

需要明确区分：

- 已设计；
- 已实现；
- 已通过自动化测试；
- 已通过真实环境验证；
- 尚未验证。

测试桩通过不代表真实 Provider、AG99 或 AG99live 已完成联机验收。

### 11.6 许可证与复用

AG99 继承了 AstrBot 相关许可证约束，AG99live 的 Live2D SDK、模型及第三方资源可能具有独立许可。

参考设计思想与直接复制代码、资源是不同的事情。

Astra 新项目应优先独立实现基础抽象，直接复用现有代码前应检查相应许可证、署名和再分发条件。

---

## 十二、第一阶段工程目标

**第一阶段最重要的目标，是验证 Component/Capability 能否支持开发者自由组织和连接多条 Workflow。**

首轮使用 Python 单进程执行，不需要完整的远程组件系统。

### Phase 0：项目初始化与能力盘点

建立独立 Astra 仓库。

整理项目愿景、术语、架构边界和参考资料。

对 AG99 与 AG99live 中的真实能力进行盘点，形成：

```text
现有功能
  → 候选 Component
  → Capability
  → 输入和输出
  → 调用方式
  → 生命周期 Owner
```

明确第一版需要验证的最小接口。

### Phase 1：最小 Component Runtime

实现：

- Component 装载与启停；
- Capability 声明；
- Capability Registry；
- Capability Resolution；
- Invoke；
- Run/Invocation 身份；
- Scope；
- Cancellation；
- 资源清理；
- 基础 Trace。

至少用两个不同 Component 提供同一种 Capability，证明调用方可以不修改自身代码就切换能力实现。

### Phase 2：多 Workflow 组合

这是第一阶段最重要的验收。

使用 Python 定义至少四条简单工作流：

**InputWorkflow**

接收和规范化输入。

**ConversationWorkflow**

模拟普通回复，并提供流式输出。

**TaskWorkflow**

模拟多步骤任务执行。

**RecordWorkflow**

订阅任务完成事件并记录结果。

运行关系：

```text
InputWorkflow
      |
    Router
    /    \
   /      \
ConversationWorkflow
          TaskWorkflow
               |
            Task Result
               |
             EventBus
               |
         RecordWorkflow
```

要求：

- 工作流能够作为 Component 注册；
- 工作流对外提供 Capability；
- Router 负责决策；
- Invoke 负责明确调用；
- Stream 负责增量数据；
- EventBus 负责事实通知；
- 工作流之间不直接依赖彼此的内部实现。

### Phase 3：运行时控制验证

覆盖：

- 父子调用取消；
- 显式长期任务；
- 流式成功、失败和取消；
- 事件订阅注销；
- Scope 停止；
- 后台任务释放；
- 迟到结果隔离；
- Capability 缺失；
- 权限拒绝；
- 副作用调用不安全重试的防护。

### Phase 4：实际领域组件适配

选择 AG99 或 AG99live 中规模较小、接口清晰的能力进行薄适配。

例如：

- 一个 Context Contributor；
- 一个简化 Persona Expression；
- 一个 AG99live 输出接口。

验证 Astra Kernel 能够承载真实领域能力，同时保持自身中立。

不要求迁移整个 AG99，也不要求重写 AG99live 的播放链路。

### Phase 5：按需求逐步扩展

后续方向包括：

- Profile / Bundle；
- Workflow IR；
- DSL；
- 可视化工作流编辑器；
- HTTP / WebSocket Component Host；
- IPC；
- Android Host；
- 热重载；
- AstrBot 兼容层；
- 远程执行与持久化任务；
- 更完整的事件机制。

这些方向应在相应需求和工程验证明确后推进。

---

## 十三、首轮验收标准

- [ ] Component 能够独立注册、启动与停止。
- [ ] Capability 能够被声明、查询和解析。
- [ ] 同一 Capability 可以替换不同实现，调用方不需要修改代码。
- [ ] 用户可以编写自定义 Workflow。
- [ ] Workflow 能够作为 Component 对外提供 Capability。
- [ ] Workflow 能够通过 Invoke 调用其他 Workflow。
- [ ] Router 能够决定执行路径。
- [ ] EventBus 能够让独立 Workflow 响应事实通知。
- [ ] Stream 支持增量输出、终态和取消。
- [ ] Scope 能正确管理订阅与资源。
- [ ] 父子执行的取消和迟到结果行为可验证。
- [ ] 有副作用的 Capability 在权限拒绝时不会执行。
- [ ] Runtime 不依赖 AG99、AstrBot、AG99live、DSH 或 Live2D 的具体类型。
- [ ] 至少有一个不依赖 LLM 的工作流演示。
- [ ] 已实现能力具有自动化测试，未验证的行为有明确说明。

---

## 十四、尚需工程验证的接口细节

| 主题 | 当前原则 | 后续需要确定 |
|---|---|---|
| Component API | 小而稳定，支持生命周期管理 | Protocol、类或函数注册方式 |
| Capability Binding | 与实现解耦，可按 Scope 解析 | 优先级、版本兼容与冲突处理 |
| Workflow | 支持代码组织和对外提供能力 | IR、DSL、序列化与可视化 |
| Router | 决策与执行分离 | 规则、LLM 或混合方式 |
| EventBus | 发布事实，订阅归属 Scope | 持久化、投递顺序、去重、重放 |
| ContextContribution | 来源和可见性明确 | 合并、优先级、时效 |
| Remote Binding | 不改变能力语义 | HTTP/WS/IPC、认证与断线恢复 |
| 权限与副作用 | 执行前需要明确授权 | 具体策略、沙箱与审批接口 |
| Agent/Persona | 可替换领域组件 | AG99 迁移与产品组合细节 |

这些接口细节通过实现和测试逐步确定，避免在缺少实际用例时过早固定复杂规范。

---

## 十五、给 Codex 的项目启动要求

请将本文作为新建 Astra 项目的架构思想与工程控制基线。

首先阅读并理解本文，检查内部概念的一致性。

随后参考以下项目：

- AG99；
- AG99live；
- Cordis；
- DeepSeek Harness；
- Vibe Engineering Cybernetics。

从中提取 Astra 真正需要的功能边界、组件行为、生命周期要求和工程控制经验。

**项目的核心目标：**

开发者可以自由组合 Component，构建不同 Workflow，并通过 Capability Invoke、Stream、Router 和 EventBus 建立明确的跨流程协作。

Workflow 和 Agent Loop 本身也可以作为 Component。

请按阶段推进：

1. 完成核心能力盘点与接口草案。
2. 建立 Python-first 本地 Component Runtime。
3. 实现多 Workflow 组合验证。
4. 验证取消、生命周期、权限和资源清理。
5. 根据测试结果调整架构。

首轮工程以单进程 Python 为范围。

公共接口变更需要说明需求依据、依赖方向、生命周期所有权和验证方式。

工程记录需要区分已实现、已测试、待验证与未来计划。

当某项设计与实际实现发生冲突时，应首先分析具体用例和最小解决方案，而不是默认增加更多抽象层。

---

## 最终项目定义

**Astra 是一个以 Component 和 Capability 为基础的可组合智能系统运行时。**

开发者能够自由组织 Workflow。工作流既能够消费其他组件提供的能力，也能够作为 Component 对外提供能力，并通过显式调用、流式连接、路由决策与事件通知进行协作。

Astra Microkernel 负责通用的注册与解析、调用因果关系、作用域、生命周期、取消、资源所有权、权限执行边界和诊断。

部署位置与传输方式不决定 Capability 的语义。

Agent、Persona、Memory、TTS、Motion、Avatar 等具体业务由组件组合实现。

**衡量 Astra 的标准是：组件接入成本低、工作流组织自由、跨流程协作可追踪、执行失败可安全收束、内核保持简洁。**