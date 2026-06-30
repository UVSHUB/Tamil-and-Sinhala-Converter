import 'dart:convert';
import 'dart:typed_data';
import 'package:flutter/foundation.dart';
import 'package:web_socket_channel/web_socket_channel.dart';
import 'package:record/record.dart';
import 'package:shared_preferences/shared_preferences.dart';

class TranslationMessage {
  final String speaker;
  final String text;

  TranslationMessage(this.speaker, this.text);

  Map<String, dynamic> toJson() => {
    'speaker': speaker,
    'text': text,
  };

  factory TranslationMessage.fromJson(Map<String, dynamic> json) {
    return TranslationMessage(json['speaker'], json['text']);
  }
}

class TranslationService extends ChangeNotifier {
  WebSocketChannel? _channel;
  final AudioRecorder _audioRecorder = AudioRecorder();
  
  bool _isRecording = false;
  bool get isRecording => _isRecording;

  List<TranslationMessage> _messages = [];
  List<TranslationMessage> get messages => _messages;

  String _sourceLanguage = 'sinhala';
  String _targetLanguage = 'tamil';

  TranslationService() {
    _loadHistory();
  }

  Future<void> _loadHistory() async {
    final prefs = await SharedPreferences.getInstance();
    final String? historyJson = prefs.getString('conversation_history');
    if (historyJson != null) {
      final List<dynamic> decodedList = jsonDecode(historyJson);
      _messages = decodedList.map((e) => TranslationMessage.fromJson(e)).toList();
      notifyListeners();
    }
  }

  Future<void> _saveHistory() async {
    final prefs = await SharedPreferences.getInstance();
    final String historyJson = jsonEncode(_messages.map((e) => e.toJson()).toList());
    await prefs.setString('conversation_history', historyJson);
  }

  Future<void> clearHistory() async {
    _messages.clear();
    await _saveHistory();
    notifyListeners();
  }

  Future<void> connect(String source, String target) async {
    _sourceLanguage = source;
    _targetLanguage = target;

    try {
      _channel = WebSocketChannel.connect(
        Uri.parse('wss://hasenalbanna-voice-translator-backend.hf.space/ws/translate'),
      );

      _channel!.stream.listen(
        (data) {
          if (data is String) {
            _handleIncomingJson(data);
          } else {
            if (kDebugMode) {
              print("Received binary audio chunk of size: ${(data as Uint8List).length}");
            }
          }
        },
        onError: (error) {
          if (kDebugMode) print("WebSocket Error: $error");
          stopRecording();
        },
        onDone: () => stopRecording(),
      );

      _sendConfig();
    } catch (e) {
      if (kDebugMode) print("Connection failed: $e");
    }
  }

  void _sendConfig() {
    if (_channel != null) {
      final configPayload = {
        "type": "update_config",
        "payload": {
          "source_language": _sourceLanguage,
          "target_language": _targetLanguage,
          "voice_synthesis_enabled": true
        }
      };
      _channel!.sink.add(jsonEncode(configPayload));
    }
  }

  void updateLanguages(String source, String target) {
    _sourceLanguage = source;
    _targetLanguage = target;
    _sendConfig();
  }

  void _handleIncomingJson(String jsonData) {
    try {
      final map = jsonDecode(jsonData);
      if (map['type'] == 'transcription' || map['type'] == 'translation') {
        final payload = map['payload'];
        final speaker = payload['speaker'];
        final text = payload['text'];

        _messages.add(TranslationMessage(speaker, text));
        _saveHistory();
        notifyListeners();
      }
    } catch (e) {
      if (kDebugMode) print("Error parsing JSON: $e");
    }
  }

  Future<void> startRecording() async {
    if (await _audioRecorder.hasPermission()) {
      try {
        final stream = await _audioRecorder.startStream(
          const RecordConfig(
            encoder: AudioEncoder.pcm16bits,
            sampleRate: 16000,
            numChannels: 1,
          ),
        );

        _isRecording = true;
        notifyListeners();

        stream.listen(
          (Uint8List data) {
            if (_channel != null && _isRecording) {
              _channel!.sink.add(data);
            }
          },
          onDone: () {
            _isRecording = false;
            notifyListeners();
          },
        );
      } catch (e) {
        if (kDebugMode) print("Error starting recorder: $e");
      }
    }
  }

  Future<void> stopRecording() async {
    if (_isRecording) {
      await _audioRecorder.stop();
      _isRecording = false;
      notifyListeners();
    }
  }

  void disconnect() {
    stopRecording();
    _channel?.sink.close();
    _channel = null;
  }
}
