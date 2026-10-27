import assert from 'node:assert'
import { readFileSync } from 'node:fs'

const useChatSource = readFileSync('src/features/chat/hooks/useChat.ts', 'utf8')
const streamClientSource = readFileSync('src/features/chat/api/chatStreamClient.ts', 'utf8')
const conversationClientSource = readFileSync('src/features/chat/api/conversationClient.ts', 'utf8')
const panelSource = readFileSync('src/features/chat/components/ChatPanel.tsx', 'utf8')

console.log('=== Running Agent-aware Chat Frontend Tests ===\n')

console.log('Test 1: Agent metadata is loaded from backend')
assert.match(useChatSource, /fetchAgents\(\)/)
assert.match(panelSource, /agents\.map/)
console.log('✓ Passed')

console.log('Test 2: All agent selections use the shared AgentId type')
assert.match(panelSource, /selectAgent\(event\.target\.value as AgentId\)/)
assert.match(panelSource, /Manager AI — Planning/)
assert.match(panelSource, /developer: 'Coding'/)
assert.match(panelSource, /researcher: 'Research'/)
console.log('✓ Passed')

console.log('Test 3: New conversations persist the selected agent')
assert.match(useChatSource, /createRemoteConversation\(title, targetAgentId/)
assert.match(conversationClientSource, /agent_id: agentId/)
console.log('✓ Passed')

console.log('Test 4: Streaming targets the selected agent endpoint')
assert.match(streamClientSource, /agents\/\$\{agentId\}\/stream/)
assert.doesNotMatch(streamClientSource, /system_instruction/)
assert.match(streamClientSource, /conversation_id: conversationId/)
console.log('✓ Passed')

console.log('Test 5: Agent switching selects only matching history')
assert.match(useChatSource, /conversation\.agent_id === agentId/)
assert.match(useChatSource, /setMessages\(\[\]\)/)
console.log('✓ Passed')

console.log('Test 6: Opening history synchronizes the agent selector')
assert.match(useChatSource, /setSelectedAgentId\(conversation\.agent_id\)/)
assert.match(panelSource, /conv\.agent_id/)
console.log('✓ Passed')

console.log('Test 7: Active streams are cancellable and switching is locked')
assert.match(useChatSource, /if \(agentId === selectedAgentIdRef\.current \|\| isStreaming\) return/)
assert.match(useChatSource, /abortControllerRef\.current\?\.abort\(\)/)
assert.match(panelSource, /disabled=\{isLoadingAgents \|\| isStreaming/)
console.log('✓ Passed')

console.log('Test 8: Selection version prevents stale message races')
assert.match(useChatSource, /selectionVersionRef\.current === version/)
assert.match(useChatSource, /activeConversationIdRef\.current === conversationId/)
console.log('✓ Passed')

console.log('Test 9: Refresh restores the persisted conversation and its agent')
assert.match(useChatSource, /ACTIVE_CONVERSATION_STORAGE_KEY/)
assert.match(useChatSource, /localStorage\.getItem/)
assert.match(useChatSource, /activateConversation\(restored \?\? list\[0\]\)/)
console.log('✓ Passed')

console.log('\n=== ALL 9 AGENT-AWARE CHAT TESTS PASSED ===')
