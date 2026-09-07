import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:share_plus/share_plus.dart';
import 'dart:math';
import 'services/translation_service.dart';

void main() {
  runApp(const TranslatorApp());
}

class MainScreen extends StatefulWidget {
  const MainScreen({super.key});

  @override
  State<MainScreen> createState() => _MainScreenState();
}

class _MainScreenState extends State<MainScreen> {
  int _currentIndex = 0;

  final List<Widget> _screens = [
    const MainTranslationScreen(),
    const Center(child: Text("Groups Screen (Beta)")),
  ];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: _screens[_currentIndex],
      bottomNavigationBar: BottomNavigationBar(
        currentIndex: _currentIndex,
        onTap: (index) {
          setState(() {
            _currentIndex = index;
          });
        },
        items: const [
          BottomNavigationBarItem(
            icon: Icon(Icons.translate),
            label: 'Translate',
          ),
          BottomNavigationBarItem(
            icon: Icon(Icons.group),
            label: 'Groups (Beta)',
          ),
        ],
      ),
    );
  }
}

class TranslatorApp extends StatelessWidget {
  const TranslatorApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Voice Translator',
      themeMode: ThemeMode.system,
      theme: ThemeData(
        brightness: Brightness.light,
        scaffoldBackgroundColor: Colors.white,
        colorScheme: const ColorScheme.light(
          primary: Colors.black,
          surface: Colors.white,
          onSurface: Colors.black,
        ),
        fontFamily: 'Roboto', 
      ),
      darkTheme: ThemeData(
        brightness: Brightness.dark,
        scaffoldBackgroundColor: Colors.black,
        colorScheme: const ColorScheme.dark(
          primary: Colors.white,
          surface: Colors.black,
          onSurface: Colors.white,
        ),
        fontFamily: 'Roboto',
      ),
      home: const MainTranslationScreen(),
      debugShowCheckedModeBanner: false,
    );
  }
}

class NoisePainter extends CustomPainter {
  final double density;
  NoisePainter({this.density = 0.15});

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = Colors.white.withOpacity(density)
      ..style = PaintingStyle.fill;
    
    final random = Random(42); 
    
    for (int i = 0; i < size.width * size.height * 0.05; i++) {
      double x = random.nextDouble() * size.width;
      double y = random.nextDouble() * size.height;
      canvas.drawRect(Rect.fromLTWH(x, y, 1, 1), paint);
    }
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}

class MainTranslationScreen extends StatefulWidget {
  const MainTranslationScreen({super.key});

  @override
  State<MainTranslationScreen> createState() => _MainTranslationScreenState();
}

class _MainTranslationScreenState extends State<MainTranslationScreen> with SingleTickerProviderStateMixin {
  final TranslationService _translationService = TranslationService();
  String sourceLang = 'sinhala';
  String targetLang = 'tamil';
  
  bool isWalkieTalkieMode = false;

  late AnimationController _animController;

  @override
  void initState() {
    super.initState();
    _animController = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 2),
    )..repeat(reverse: true);

    _translationService.connect(sourceLang, targetLang);
    _translationService.addListener(() {
      setState(() {});
    });
  }

  @override
  void dispose() {
    _translationService.disconnect();
    _translationService.dispose();
    _animController.dispose();
    super.dispose();
  }

  void _toggleRecording() {
    if (!isWalkieTalkieMode) {
      if (_translationService.isRecording) {
        _translationService.stopRecording();
      } else {
        _translationService.startRecording();
      }
    }
  }

  void _onLongPressStart(LongPressStartDetails details) {
    if (isWalkieTalkieMode) {
      _translationService.startRecording();
    }
  }

  void _onLongPressEnd(LongPressEndDetails details) {
    if (isWalkieTalkieMode) {
      _translationService.stopRecording();
    }
  }
  
  void _swapLanguages() {
    setState(() {
      final temp = sourceLang;
      sourceLang = targetLang;
      targetLang = temp;
      _translationService.updateLanguages(sourceLang, targetLang);
    });
  }

  void _copyToClipboard(String text) {
    Clipboard.setData(ClipboardData(text: text));
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text("Copied to clipboard!"),
        duration: Duration(seconds: 2),
      )
    );
  }

  void _shareText(String text) {
    Share.share(text, subject: 'Translated Text');
  }

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    
    return Scaffold(
      body: Stack(
        children: [
          if (isDark)
            Positioned.fill(
              child: Opacity(
                opacity: 0.15,
                child: CustomPaint(painter: NoisePainter(density: 0.15)),
              ),
            ),
          
          SafeArea(
            child: Column(
              children: [
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Row(
                        children: [
                          IconButton(
                            icon: Icon(isWalkieTalkieMode ? Icons.chat : Icons.waves, color: isDark ? Colors.white70 : Colors.black87),
                            onPressed: () {
                              setState(() {
                                isWalkieTalkieMode = !isWalkieTalkieMode;
                              });
                              ScaffoldMessenger.of(context).showSnackBar(
                                SnackBar(
                                  content: Text(isWalkieTalkieMode ? "Walkie-Talkie Mode Enabled" : "Continuous Mode Enabled"),
                                  duration: const Duration(seconds: 2),
                                )
                              );
                            },
                            tooltip: "Toggle Walkie-Talkie Mode",
                          ),
                          IconButton(
                            icon: Icon(Icons.delete_outline, color: isDark ? Colors.white70 : Colors.black87),
                            onPressed: () {
                              _translationService.clearHistory();
                            },
                            tooltip: "Clear History",
                          ),
                        ],
                      ),
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                        decoration: BoxDecoration(
                          color: isDark ? Colors.white10 : Colors.black12,
                          borderRadius: BorderRadius.circular(20),
                        ),
                        child: Row(
                          children: [
                            Container(
                              width: 8,
                              height: 8,
                              decoration: const BoxDecoration(
                                color: Colors.green,
                                shape: BoxShape.circle,
                              ),
                            ),
                            const SizedBox(width: 8),
                            const Text("Live", style: TextStyle(fontSize: 12, fontWeight: FontWeight.w500)),
                          ],
                        ),
                      )
                    ],
                  ),
                ),
                
                GestureDetector(
                  onTap: _swapLanguages,
                  child: Container(
                    margin: const EdgeInsets.symmetric(vertical: 10),
                    padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
                    decoration: BoxDecoration(
                      border: Border.all(color: isDark ? Colors.white24 : Colors.black12),
                      borderRadius: BorderRadius.circular(30),
                    ),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(sourceLang.toUpperCase(), style: const TextStyle(fontWeight: FontWeight.bold)),
                        const Padding(
                          padding: EdgeInsets.symmetric(horizontal: 16),
                          child: Icon(Icons.swap_horiz, size: 20),
                        ),
                        Text(targetLang.toUpperCase(), style: const TextStyle(fontWeight: FontWeight.bold)),
                      ],
                    ),
                  ),
                ),

                Expanded(
                  child: ListView.builder(
                    padding: const EdgeInsets.symmetric(horizontal: 24),
                    reverse: true,
                    itemCount: _translationService.messages.length,
                    itemBuilder: (context, index) {
                      final item = _translationService.messages[_translationService.messages.length - 1 - index];
                      final isAI = item.speaker == 'ai';
                      return GestureDetector(
                        onTap: () => _copyToClipboard(item.text),
                        child: Container(
                          margin: const EdgeInsets.only(bottom: 24),
                          alignment: isAI ? Alignment.centerRight : Alignment.centerLeft,
                          child: Column(
                            crossAxisAlignment: isAI ? CrossAxisAlignment.end : CrossAxisAlignment.start,
                            children: [
                              Row(
                                mainAxisSize: MainAxisSize.min,
                                children: [
                                  if (!isAI)
                                    IconButton(
                                      icon: Icon(Icons.share, size: 14, color: isDark ? Colors.white54 : Colors.black54),
                                      padding: EdgeInsets.zero,
                                      constraints: const BoxConstraints(),
                                      onPressed: () => _shareText(item.text),
                                    ),
                                  if (!isAI) const SizedBox(width: 4),
                                  Text(
                                    isAI ? targetLang.toUpperCase() : sourceLang.toUpperCase(),
                                    style: TextStyle(
                                      fontSize: 10, 
                                      fontWeight: FontWeight.w600, 
                                      color: isDark ? Colors.white54 : Colors.black54
                                    ),
                                  ),
                                  if (isAI) const SizedBox(width: 4),
                                  if (isAI)
                                    IconButton(
                                      icon: Icon(Icons.share, size: 14, color: isDark ? Colors.white54 : Colors.black54),
                                      padding: EdgeInsets.zero,
                                      constraints: const BoxConstraints(),
                                      onPressed: () => _shareText(item.text),
                                    ),
                                ],
                              ),
                              const SizedBox(height: 4),
                              Text(
                                item.text,
                                style: TextStyle(
                                  fontSize: 22,
                                  fontWeight: isAI ? FontWeight.w400 : FontWeight.w600,
                                  color: isDark ? Colors.white : Colors.black,
                                ),
                              ),
                            ],
                          ),
                        ),
                      );
                    },
                  ),
                ),

                Container(
                  height: 160,
                  alignment: Alignment.center,
                  child: Stack(
                    alignment: Alignment.center,
                    children: [
                      if (_translationService.isRecording)
                        AnimatedBuilder(
                          animation: _animController,
                          builder: (context, child) {
                            return Container(
                              width: 100 + (_animController.value * 40),
                              height: 100 + (_animController.value * 40),
                              decoration: BoxDecoration(
                                shape: BoxShape.circle,
                                color: (isDark ? Colors.white : Colors.black).withOpacity(0.1 - (_animController.value * 0.1)),
                              ),
                            );
                          },
                        ),
                      
                      GestureDetector(
                        onTap: _toggleRecording,
                        onLongPressStart: _onLongPressStart,
                        onLongPressEnd: _onLongPressEnd,
                        child: AnimatedContainer(
                          duration: const Duration(milliseconds: 300),
                          width: 80,
                          height: 80,
                          decoration: BoxDecoration(
                            shape: BoxShape.circle,
                            color: isDark ? Colors.white : Colors.black,
                            boxShadow: [
                              if (_translationService.isRecording)
                                BoxShadow(
                                  color: isDark ? Colors.white24 : Colors.black26,
                                  blurRadius: 20,
                                  spreadRadius: 5,
                                )
                            ]
                          ),
                          child: Icon(
                            _translationService.isRecording ? Icons.stop : Icons.mic,
                            color: isDark ? Colors.black : Colors.white,
                            size: 32,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
                Text(
                  isWalkieTalkieMode ? "Hold to speak" : "Tap to record",
                  style: TextStyle(color: isDark ? Colors.white54 : Colors.black54, fontSize: 12),
                ),
                const SizedBox(height: 16),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
