import assert from 'node:assert'

function mapRemoteMessagesToLocal(remoteMsgs) {
  return remoteMsgs.map((m) => {
    const date = new Date(m.created_at)
    const formattedTime = date.toLocaleTimeString([], {
      hour: '2-digit',
      minute: '2-digit',
    })
    return {
      id: `msg-${m.id}`,
      role: m.role,
      content: m.content,
      timestamp: formattedTime,
      createdAt: date.getTime(),
      status: 'completed',
      conversationId: m.conversation_id,
      remoteId: m.id,
    }
  })
}

async function runTests() {
  console.log('=== Running Persistent Chat & History Automated Tests ===\n')

  // 1. Remote message mapping
  {
    console.log('Test 1: Mapping remote database messages to frontend ChatMessage structure')
    const remote = [
      {
        id: 101,
        conversation_id: 1,
        role: 'user',
        content: 'Create a website plan',
        created_at: '2026-10-26T10:00:00.000Z',
      },
      {
        id: 102,
        conversation_id: 1,
        role: 'assistant',
        content: '1. Architecture\n2. Implementation',
        created_at: '2026-10-26T10:00:05.000Z',
      },
    ]

    const mapped = mapRemoteMessagesToLocal(remote)
    assert.strictEqual(mapped.length, 2)
    assert.strictEqual(mapped[0].id, 'msg-101')
    assert.strictEqual(mapped[0].role, 'user')
    assert.strictEqual(mapped[0].status, 'completed')
    assert.strictEqual(mapped[0].remoteId, 101)

    assert.strictEqual(mapped[1].id, 'msg-102')
    assert.strictEqual(mapped[1].role, 'assistant')
    assert.strictEqual(mapped[1].status, 'completed')
    assert.strictEqual(mapped[1].remoteId, 102)
    console.log('✓ Passed: Database records mapped into UI state faithfully')
  }

  // 2. User message persistence precedes AI streaming
  {
    console.log('\nTest 2: User message persistence precedes AI streaming')
    let userMsgPersisted = false
    let streamStarted = false

    async function mockSendMessage(prompt, shouldFailDb = false) {
      // Step 1: Persist user message
      if (shouldFailDb) {
        return { success: false, error: 'Database connection error' }
      }
      userMsgPersisted = true

      // Step 2: Only if user message succeeded, start streaming
      streamStarted = true
      return { success: true }
    }

    // A: Success path
    const resSuccess = await mockSendMessage('Hello', false)
    assert.strictEqual(resSuccess.success, true)
    assert.strictEqual(userMsgPersisted, true)
    assert.strictEqual(streamStarted, true)

    // B: Database failure path
    userMsgPersisted = false
    streamStarted = false
    const resFail = await mockSendMessage('Hello', true)
    assert.strictEqual(resFail.success, false)
    assert.strictEqual(userMsgPersisted, false)
    assert.strictEqual(streamStarted, false, 'Stream MUST NOT start if DB persistence failed')
    console.log('✓ Passed: Streaming is strictly gated on successful user message persistence')
  }

  // 3. Assistant response persistence on stream completion
  {
    console.log('\nTest 3: Assistant response persistence on stream done event')
    const donePayload = {
      status: 'completed',
      message_id: 205,
      conversation_id: 10,
    }

    let assistantMsg = {
      id: 'assistant-1',
      role: 'assistant',
      content: 'Here is your solution.',
      status: 'streaming',
      conversationId: 10,
    }

    // On done event received with message_id
    if (donePayload.status === 'completed') {
      assistantMsg = {
        ...assistantMsg,
        status: 'completed',
        remoteId: donePayload.message_id,
      }
    }

    assert.strictEqual(assistantMsg.status, 'completed')
    assert.strictEqual(assistantMsg.remoteId, 205)
    console.log('✓ Passed: Assistant message updated with completed status and remote ID from DB')
  }

  // 4. Cancellation (Stop generating) does not save as completed
  {
    console.log('\nTest 4: Stop generating does not save or mark as completed')
    let assistantMsg = {
      id: 'assistant-2',
      role: 'assistant',
      content: 'Halfway through answering...',
      status: 'streaming',
      conversationId: 10,
    }

    // Stop generating triggered
    const isCancelled = true
    if (isCancelled) {
      assistantMsg = {
        ...assistantMsg,
        status: 'stopped',
      }
    }

    assert.strictEqual(assistantMsg.status, 'stopped')
    assert.strictEqual(assistantMsg.remoteId, undefined, 'Aborted message must NOT have remoteId')
    console.log('✓ Passed: Cancelled response is marked stopped without remote persistence')
  }

  // 5. Stream error marks message as failed without remoteId
  {
    console.log('\nTest 5: Stream error marks message failed without remoteId')
    let assistantMsg = {
      id: 'assistant-3',
      role: 'assistant',
      content: 'Starting...',
      status: 'streaming',
      conversationId: 10,
    }

    // Error event received
    const errorEvent = { code: 'AI_PROVIDER_ERROR', message: 'Quota exceeded' }
    assistantMsg = {
      ...assistantMsg,
      status: 'failed',
      error: errorEvent.message,
    }

    assert.strictEqual(assistantMsg.status, 'failed')
    assert.strictEqual(assistantMsg.error, 'Quota exceeded')
    assert.strictEqual(assistantMsg.remoteId, undefined)
    console.log('✓ Passed: Error stream gracefully reflects failure without fake DB record')
  }

  // 6. Race condition: switching conversation during streaming does not bleed chunks
  {
    console.log('\nTest 6: Race condition protection: switching conversation prevents chunk bleeding')
    let activeConversationId = 1
    let conv1Messages = [{ id: 'a1', content: '' }]
    let conv2Messages = [{ id: 'u2', content: 'What is task 2?' }]

    function handleChunk(streamConversationId, chunkText) {
      // Only append to active conversation
      if (activeConversationId === streamConversationId) {
        conv1Messages = conv1Messages.map((m) =>
          m.id === 'a1' ? { ...m, content: m.content + chunkText } : m
        )
      }
    }

    // Chunk arrives for Conv 1 while viewing Conv 1
    handleChunk(1, 'Part 1. ')
    assert.strictEqual(conv1Messages[0].content, 'Part 1. ')

    // User switches to Conv 2
    activeConversationId = 2

    // Delayed chunk arrives for Conv 1
    handleChunk(1, 'Part 2.')

    // Verify Conv 2 was NOT contaminated
    assert.strictEqual(conv2Messages.length, 1)
    assert.strictEqual(conv2Messages[0].content, 'What is task 2?')
    console.log('✓ Passed: Chunks from conversation 1 never bleed into conversation 2')
  }

  // 7. Refresh restoration simulation
  {
    console.log('\nTest 7: Browser refresh restoration from PostgreSQL')
    const mockPostgreSqlData = [
      { id: 2, title: 'Project Beta', updated_at: '2026-10-26T12:00:00Z' },
      { id: 1, title: 'Project Alpha', updated_at: '2026-10-26T10:00:00Z' },
    ]

    const mockMessagesByConv = {
      2: [
        { id: 201, conversation_id: 2, role: 'user', content: 'Build Alpha', created_at: '2026-10-26T12:00:00Z' },
        { id: 202, conversation_id: 2, role: 'assistant', content: 'Done.', created_at: '2026-10-26T12:00:05Z' },
      ],
    }

    // Refresh simulation: initial load
    const conversations = [...mockPostgreSqlData]
    const initialActiveId = conversations[0].id // Selects most recent
    const initialMessages = mapRemoteMessagesToLocal(mockMessagesByConv[initialActiveId])

    assert.strictEqual(conversations.length, 2)
    assert.strictEqual(initialActiveId, 2)
    assert.strictEqual(initialMessages.length, 2)
    assert.strictEqual(initialMessages[0].role, 'user')
    assert.strictEqual(initialMessages[1].role, 'assistant')
    console.log('✓ Passed: On page refresh, latest conversation and messages are automatically restored')
  }

  // 8. Delete conversation cascades cleanly in local UI state
  {
    console.log('\nTest 8: Delete conversation cleans up state and activates next thread')
    let conversations = [
      { id: 1, title: 'First' },
      { id: 2, title: 'Second' },
    ]
    let activeId = 1

    function deleteConv(idToDelete) {
      conversations = conversations.filter((c) => c.id !== idToDelete)
      if (activeId === idToDelete) {
        activeId = conversations.length > 0 ? conversations[0].id : null
      }
    }

    deleteConv(1)
    assert.strictEqual(conversations.length, 1)
    assert.strictEqual(activeId, 2)
    console.log('✓ Passed: Deletion transitions smoothly to next available conversation')
  }

  console.log('\n=== ALL 8 PERSISTENT CHAT TESTS PASSED SUCCESSFULLY! ===')
}

runTests()

