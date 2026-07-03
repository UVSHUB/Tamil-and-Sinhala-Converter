import 'package:flutter/material.dart';
import 'chat_screen.dart';

class GroupsScreen extends StatefulWidget {
  const GroupsScreen({Key? key}) : super(key: key);

  @override
  _GroupsScreenState createState() => _GroupsScreenState();
}

class _GroupsScreenState extends State<GroupsScreen> {
  // Placeholder data for the WhatsApp-style list
  final List<Map<String, String>> _groups = [
    {"id": "1", "name": "Family Translators", "last_message": "Dad: Hello!"},
    {"id": "2", "name": "Work Team", "last_message": "Alice: Is the meeting at 5?"},
  ];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('My Groups'),
        actions: [
          IconButton(
            icon: const Icon(Icons.person),
            onPressed: () {
              // TODO: Navigate to User Profile / Username setup
            },
          ),
        ],
      ),
      body: ListView.builder(
        itemCount: _groups.length,
        itemBuilder: (context, index) {
          final group = _groups[index];
          return ListTile(
            leading: CircleAvatar(
              backgroundColor: Theme.of(context).primaryColor,
              child: Text(group["name"]![0].toUpperCase(), style: const TextStyle(color: Colors.white)),
            ),
            title: Text(group["name"]!, style: const TextStyle(fontWeight: FontWeight.bold)),
            subtitle: Text(group["last_message"]!),
            trailing: const Icon(Icons.chevron_right),
            onTap: () {
              Navigator.push(
                context,
                MaterialPageRoute(
                  builder: (context) => ChatScreen(
                    groupId: group["id"]!,
                    groupName: group["name"]!,
                  ),
                ),
              );
            },
          );
        },
      ),
      floatingActionButton: FloatingActionButton(
        onPressed: () {
          // TODO: Add group creation dialog
        },
        child: const Icon(Icons.group_add),
      ),
    );
  }
}
