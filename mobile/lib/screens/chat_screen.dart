import 'package:flutter/material.dart';

class ChatScreen extends StatefulWidget {
  final String groupId;
  final String groupName;

  const ChatScreen({
    Key? key,
    required this.groupId,
    required this.groupName,
  }) : super(key: key);

  @override
  _ChatScreenState createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> {
  final TextEditingController _textController = TextEditingController();
  final List<Map<String, dynamic>> _messages = [
    {"isMe": false, "sender": "Alice", "text": "Hi everyone!"},
    {"isMe": true, "sender": "Me", "text": "Hello!"},
  ];

  void _handleSubmitted(String text) {
    if (text.trim().isEmpty) return;
    _textController.clear();
    setState(() {
      _messages.add({"isMe": true, "sender": "Me", "text": text});
    });
    // TODO: Send over WebSocket to backend
  }

  void _startGroupCall() {
    // TODO: Connect to backend Gemini voice routing
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text("Connecting to Group Audio Call with Live Translation...")),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(widget.groupName),
        actions: [
          IconButton(
            icon: const Icon(Icons.call),
            onPressed: _startGroupCall,
          ),
          IconButton(
            icon: const Icon(Icons.more_vert),
            onPressed: () {
              // TODO: Show group info & 20 features menu
            },
          ),
        ],
      ),
      body: Column(
        children: [
          Expanded(
            child: ListView.builder(
              padding: const EdgeInsets.all(8.0),
              itemCount: _messages.length,
              itemBuilder: (context, index) {
                final msg = _messages[index];
                final isMe = msg["isMe"] as bool;
                return Container(
                  margin: const EdgeInsets.symmetric(vertical: 4.0),
                  alignment: isMe ? Alignment.centerRight : Alignment.centerLeft,
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 14.0, vertical: 10.0),
                    decoration: BoxDecoration(
                      color: isMe ? Theme.of(context).primaryColor : Colors.grey[300],
                      borderRadius: BorderRadius.circular(15.0),
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        if (!isMe)
                          Text(
                            msg["sender"],
                            style: TextStyle(
                              fontSize: 12,
                              fontWeight: FontWeight.bold,
                              color: Colors.black54,
                            ),
                          ),
                        Text(
                          msg["text"],
                          style: TextStyle(color: isMe ? Colors.white : Colors.black),
                        ),
                      ],
                    ),
                  ),
                );
              },
            ),
          ),
          const Divider(height: 1.0),
          Container(
            decoration: BoxDecoration(color: Theme.of(context).cardColor),
            child: Row(
              children: [
                IconButton(
                  icon: const Icon(Icons.attach_file),
                  onPressed: () {},
                ),
                Expanded(
                  child: TextField(
                    controller: _textController,
                    decoration: const InputDecoration.collapsed(hintText: 'Type a message...'),
                    onSubmitted: _handleSubmitted,
                  ),
                ),
                IconButton(
                  icon: const Icon(Icons.send),
                  onPressed: () => _handleSubmitted(_textController.text),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
