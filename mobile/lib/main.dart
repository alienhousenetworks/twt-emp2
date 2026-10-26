import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:http/http.dart' as http;

const baseUrl = String.fromEnvironment('FRAPPE_URL', defaultValue: 'http://10.0.2.2:8000');
const secureStorage = FlutterSecureStorage();
final api = WorkforceApi();

void main() => runApp(const WorkforceApp());

class WorkforceApi {
  Future<Map<String, String>> headers() async {
    final sid = await secureStorage.read(key: 'sid');
    final csrf = await secureStorage.read(key: 'csrf_token');
    return {
      'Content-Type': 'application/json',
      if (sid != null && sid.isNotEmpty) 'Cookie': 'sid=' + sid,
      if (csrf != null && csrf.isNotEmpty) 'X-Frappe-CSRF-Token': csrf,
    };
  }

  Future<dynamic> call(String method, {Map<String, dynamic>? args}) async {
    final uri = Uri.parse(baseUrl + '/api/method/agency_workforce_os.api.' + method);
    final h = await headers();
    final response = args == null
        ? await http.get(uri, headers: h)
        : await http.post(uri, headers: h, body: jsonEncode(args));
    final decoded = jsonDecode(response.body);
    if (response.statusCode < 200 || response.statusCode >= 300 || decoded['exc'] != null) {
      throw Exception(decoded['message'] ?? decoded['exception'] ?? 'Request failed (' + response.statusCode.toString() + ')');
    }
    return decoded['message'];
  }

  Future<void> login(String username, String password) async {
    final response = await http.post(
      Uri.parse(baseUrl + '/api/method/login'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'usr': username, 'pwd': password}),
    );
    final decoded = jsonDecode(response.body);
    if (response.statusCode < 200 || response.statusCode >= 300 || decoded['exc'] != null) {
      throw Exception(decoded['message'] ?? 'Login failed. Verify the credentials and server URL.');
    }
    final cookie = response.headers['set-cookie'] ?? '';
    final match = RegExp(r'sid=([^;]+)').firstMatch(cookie);
    final sid = match?.group(1) ?? decoded['sid']?.toString();
    if (sid == null || sid.isEmpty) {
      throw Exception('Frappe did not return a session cookie. Check reverse proxy cookie forwarding.');
    }
    await secureStorage.write(key: 'sid', value: sid);
    if (decoded['csrf_token'] != null) {
      await secureStorage.write(key: 'csrf_token', value: decoded['csrf_token'].toString());
    }
  }

  Future<void> logout() async {
    try {
      await http.post(Uri.parse(baseUrl + '/api/method/logout'), headers: await headers());
    } catch (_) {}
    await secureStorage.delete(key: 'sid');
    await secureStorage.delete(key: 'csrf_token');
  }
}

class WorkforceApp extends StatelessWidget {
  const WorkforceApp({super.key});
  @override
  Widget build(BuildContext context) => MaterialApp(
    title: 'Agency Workforce OS',
    debugShowCheckedModeBanner: false,
    theme: ThemeData(
      colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xffc9fa68)),
      useMaterial3: true,
      scaffoldBackgroundColor: const Color(0xfff5f7f3),
    ),
    home: const AuthGate(),
  );
}

class AuthGate extends StatefulWidget {
  const AuthGate({super.key});
  @override
  State<AuthGate> createState() => _AuthGateState();
}
class _AuthGateState extends State<AuthGate> {
  bool loading = true;
  bool authenticated = false;
  @override
  void initState() { super.initState(); _check(); }
  Future<void> _check() async {
    try { await api.call('get_workspace'); authenticated = true; } catch (_) { authenticated = false; }
    if (mounted) setState(() => loading = false);
  }
  @override
  Widget build(BuildContext context) => loading
      ? const Scaffold(body: Center(child: CircularProgressIndicator()))
      : authenticated ? const WorkspaceShell() : const LoginPage();
}

class LoginPage extends StatefulWidget {
  const LoginPage({super.key});
  @override
  State<LoginPage> createState() => _LoginPageState();
}
class _LoginPageState extends State<LoginPage> {
  final username = TextEditingController();
  final password = TextEditingController();
  bool busy = false;
  String? error;
  Future<void> submit() async {
    setState(() { busy = true; error = null; });
    try {
      await api.login(username.text.trim(), password.text);
      await api.call('get_workspace');
      if (mounted) Navigator.of(context).pushReplacement(MaterialPageRoute(builder: (_) => const WorkspaceShell()));
    } catch (e) { if (mounted) setState(() => error = e.toString()); }
    finally { if (mounted) setState(() => busy = false); }
  }
  @override
  void dispose() { username.dispose(); password.dispose(); super.dispose(); }
  @override
  Widget build(BuildContext context) => Scaffold(
    body: Center(child: SingleChildScrollView(padding: const EdgeInsets.all(24), child: ConstrainedBox(
      constraints: const BoxConstraints(maxWidth: 420), child: Card(child: Padding(
        padding: const EdgeInsets.all(24), child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          const Icon(Icons.hub_outlined, size: 48), const SizedBox(height: 12),
          Text('Agency Workforce OS', textAlign: TextAlign.center, style: Theme.of(context).textTheme.headlineSmall),
          const SizedBox(height: 8), const Text('Sign in with your company Frappe account.', textAlign: TextAlign.center),
          const SizedBox(height: 22),
          TextField(controller: username, autocorrect: false, decoration: const InputDecoration(labelText: 'Email or username', border: OutlineInputBorder())),
          const SizedBox(height: 12),
          TextField(controller: password, obscureText: true, decoration: const InputDecoration(labelText: 'Password', border: OutlineInputBorder()), onSubmitted: (_) => submit()),
          if (error != null) Padding(padding: const EdgeInsets.only(top: 12), child: Text(error!, style: TextStyle(color: Theme.of(context).colorScheme.error))),
          const SizedBox(height: 16), FilledButton(onPressed: busy ? null : submit, child: Text(busy ? 'Signing in…' : 'Sign in')),
          const SizedBox(height: 12), const Text('Set the server with --dart-define=FRAPPE_URL=https://your-frappe-host', style: TextStyle(fontSize: 11, color: Colors.grey)),
        ]),
      )),
    ))),
  );
}

class WorkspaceShell extends StatefulWidget {
  const WorkspaceShell({super.key});
  @override
  State<WorkspaceShell> createState() => _WorkspaceShellState();
}
class _WorkspaceShellState extends State<WorkspaceShell> {
  final pages = const ['Home', 'Feed', 'Tasks', 'EOD', 'People', 'Leave', 'Projects', 'CRM', 'Profile'];
  int index = 0;
  bool loading = true;
  String? error;
  Map<String, dynamic>? workspace;
  List<dynamic> rows = [];
  List<String> leaveTypes = [];
  final composer = TextEditingController();
  final completed = TextEditingController(), pending = TextEditingController(), blockers = TextEditingController(), nextDay = TextEditingController(), helpNeeded = TextEditingController();
  final leaveReason = TextEditingController(), leaveFrom = TextEditingController(), leaveTo = TextEditingController();
  String leaveType = '';
  Future<void> load() async {
    setState(() { loading = true; error = null; });
    try {
      workspace = Map<String, dynamic>.from(await api.call('get_workspace'));
      rows = [];
      if (index == 3) rows = await api.call('list_eod_reports');
      if (index == 4) rows = (await api.call('list_employees'))['employees'] ?? [];
      if (index == 5) {
        final results = await Future.wait([api.call('list_my_attendance'), api.call('list_my_leave'), api.call('list_leave_types')]);
        rows = [...(results[0] as List).map((x) => {...Map<String,dynamic>.from(x), '_kind':'Attendance'}),
          ...(results[1] as List).map((x) => {...Map<String,dynamic>.from(x), '_kind':'Leave'})];
        leaveTypes = (results[2] as List).map((x) => x['name'].toString()).toList();
        if (leaveType.isEmpty && leaveTypes.isNotEmpty) leaveType = leaveTypes.first;
      }
      if (index == 6) rows = await api.call('list_projects');
      if (index == 7) rows = await api.call('list_crm_records', args: {'doctype':'Lead'});
    } catch (e) { error = e.toString(); }
    if (mounted) setState(() => loading = false);
  }
  Future<void> publish() async {
    try { await api.call('create_feed_post', args: {'content':composer.text.trim(),'post_type':'General Update','visibility':'Team'}); composer.clear(); await load(); }
    catch (e) { setState(() => error = e.toString()); }
  }
  Future<void> submitEod() async {
    try {
      await api.call('submit_eod', args: {'report_date':DateTime.now().toIso8601String().substring(0,10),'completed_work':completed.text,'pending_work':pending.text,'blockers':blockers.text,'next_day_plan':nextDay.text,'help_needed':helpNeeded.text});
      for (final c in [completed,pending,blockers,nextDay,helpNeeded]) { c.clear(); }
      await load();
    } catch (e) { setState(() => error = e.toString()); }
  }
  Future<void> submitLeave() async {
    try { await api.call('request_leave', args: {'leave_type':leaveType,'from_date':leaveFrom.text,'to_date':leaveTo.text,'reason':leaveReason.text}); leaveReason.clear(); await load(); }
    catch (e) { setState(() => error = e.toString()); }
  }
  @override
  void initState() { super.initState(); load(); }
  @override
  void dispose() { composer.dispose(); completed.dispose(); pending.dispose(); blockers.dispose(); nextDay.dispose(); helpNeeded.dispose(); leaveReason.dispose(); leaveFrom.dispose(); leaveTo.dispose(); super.dispose(); }
  @override
  Widget build(BuildContext context) {
    final tasks = workspace?['tasks'] as List? ?? const [];
    final feed = workspace?['feed'] as List? ?? const [];
    final employee = workspace?['employee'] as Map<String,dynamic>?;
    return Scaffold(
      appBar: AppBar(title: Text('Agency OS · ' + pages[index]), actions: [
        IconButton(onPressed: load, icon: const Icon(Icons.refresh)),
        PopupMenuButton<String>(onSelected: (v) async { if (v == 'logout') { await api.logout(); if (mounted) Navigator.of(context).pushAndRemoveUntil(MaterialPageRoute(builder: (_) => const LoginPage()), (_) => false); } }, itemBuilder: (_) => const [PopupMenuItem(value:'logout', child:Text('Sign out'))]),
      ]),
      body: RefreshIndicator(onRefresh: load, child: ListView(padding: const EdgeInsets.all(16), children: [
        if (loading) const LinearProgressIndicator(),
        if (error != null) Padding(padding: const EdgeInsets.only(bottom:12), child: Text(error!, style: TextStyle(color:Theme.of(context).colorScheme.error))),
        if (index == 0) ...[
          Text('Welcome, ' + (employee?['employee_name']?.toString() ?? 'team member'), style:Theme.of(context).textTheme.headlineSmall),
          Text(employee?['department']?.toString() ?? 'Employee workspace'),
          Row(children:[Expanded(child:_metric('My tasks',tasks.length.toString())),Expanded(child:_metric('Feed updates',feed.length.toString()))]),
          const SizedBox(height:12), const Text('Recent tasks',style:TextStyle(fontWeight:FontWeight.bold)),
          for (final t in tasks.take(5)) _task(t),
        ],
        if (index == 1) ...[
          TextField(controller:composer,maxLines:3,maxLength:10000,decoration:const InputDecoration(border:OutlineInputBorder(),hintText:'Share progress or a blocker')),
          Align(alignment:Alignment.centerRight,child:FilledButton(onPressed:composer.text.trim().isEmpty?null:publish,child:const Text('Publish update'))),
          for (final p in feed) _feedCard(p),
        ],
        if (index == 2) ...[for (final t in tasks) _task(t)],
        if (index == 3) ...[
          Text('Daily EOD report',style:Theme.of(context).textTheme.titleLarge),
          _field(completed,'Completed work *'),_field(pending,'Pending work'),_field(blockers,'Blockers and risks'),_field(nextDay,'Next day plan'),_field(helpNeeded,'Help needed'),
          FilledButton(onPressed:completed.text.trim().isEmpty?null:submitEod,child:const Text('Submit EOD')),
          const Divider(height:32), const Text('Report history',style:TextStyle(fontWeight:FontWeight.bold)),
          for(final r in rows) ListTile(title:Text(r['employee_name']?.toString()??r['employee']?.toString()??'EOD report'),subtitle:Text(r['report_date'].toString()),trailing:Text(r['status']?.toString()??'')),
        ],
        if (index == 4) ...[const Text('Employee directory',style:TextStyle(fontWeight:FontWeight.bold)),for(final p in rows) ListTile(leading:const CircleAvatar(child:Icon(Icons.person)),title:Text(p['employee_name']?.toString()??p['name']?.toString()??'Employee'),subtitle:Text((p['department']??'No department').toString()+' · '+(p['designation']??'').toString()),trailing:Text(p['status']?.toString()??''))],
        if (index == 5) ...[
          Text('Request leave',style:Theme.of(context).textTheme.titleLarge),
          DropdownButtonFormField<String>(value:leaveTypes.contains(leaveType)?leaveType:null,items:leaveTypes.map((x)=>DropdownMenuItem(value:x,child:Text(x))).toList(),onChanged:(v)=>setState(()=>leaveType=v??''),decoration:const InputDecoration(labelText:'Leave type')),
          _field(leaveFrom,'From date (YYYY-MM-DD)'),_field(leaveTo,'To date (YYYY-MM-DD)'),_field(leaveReason,'Reason'),
          FilledButton(onPressed:leaveType.isEmpty||leaveFrom.text.isEmpty||leaveTo.text.isEmpty||leaveReason.text.trim().isEmpty?null:submitLeave,child:const Text('Submit leave request')),
          const Divider(height:30),const Text('Attendance and leave history',style:TextStyle(fontWeight:FontWeight.bold)),
          for(final r in rows) ListTile(leading:Icon(r['_kind']=='Attendance'?Icons.event_available:Icons.beach_access),title:Text(r['_kind']=='Attendance'?(r['attendance_date']??'Attendance').toString():(r['leave_type']??'Leave').toString()),subtitle:Text(r['_kind']=='Attendance'?(r['shift']??'').toString():(r['from_date'].toString()+' → '+r['to_date'].toString())),trailing:Text(r['status']?.toString()??'')),
        ],
        if (index == 6) ...[const Text('Projects',style:TextStyle(fontWeight:FontWeight.bold)),for(final p in rows) ListTile(leading:const Icon(Icons.folder_open),title:Text(p['project_name']?.toString()??p['name']?.toString()??'Project'),subtitle:Text(p['status']?.toString()??'Status unavailable'),trailing:Text((p['percent_complete']??'—').toString()+'%'))],
        if (index == 7) ...[const Text('CRM leads',style:TextStyle(fontWeight:FontWeight.bold)),for(final l in rows) ListTile(leading:const Icon(Icons.person_search),title:Text(l['lead_name']?.toString()??l['name']?.toString()??'Lead'),subtitle:Text(l['company_name']?.toString()??''),trailing:Text(l['status']?.toString()??''))],
        if (index == 8) ...[const Icon(Icons.account_circle_outlined,size:56),Text(employee?['employee_name']?.toString()??'Employee',textAlign:TextAlign.center,style:Theme.of(context).textTheme.titleLarge),Text((employee?['designation']??'Role not set').toString()+' · '+(employee?['department']??'Department not set').toString(),textAlign:TextAlign.center),const SizedBox(height:16),const Text('Profile and HR records are managed in ERPNext.',textAlign:TextAlign.center)],
      ])),
      bottomNavigationBar: NavigationBar(selectedIndex:index,onDestinationSelected:(v){setState(()=>index=v);load();},destinations:const[
        NavigationDestination(icon:Icon(Icons.home_outlined),label:'Home'),
        NavigationDestination(icon:Icon(Icons.dynamic_feed_outlined),label:'Feed'),
        NavigationDestination(icon:Icon(Icons.task_alt),label:'Tasks'),
        NavigationDestination(icon:Icon(Icons.summarize_outlined),label:'EOD'),
        NavigationDestination(icon:Icon(Icons.people_outline),label:'People'),
      ]),
    );
  }
  Widget _field(TextEditingController c,String label)=>Padding(padding:const EdgeInsets.symmetric(vertical:6),child:TextField(controller:c, maxLines: label.contains('Reason')||label.contains('work')||label.contains('blockers')||label.contains('plan')||label.contains('needed')?3:1,decoration:InputDecoration(labelText:label,border:const OutlineInputBorder())));
  Widget _metric(String label,String value)=>Card(child:Padding(padding:const EdgeInsets.all(16),child:Column(crossAxisAlignment:CrossAxisAlignment.start,children:[Text(label),const SizedBox(height:8),Text(value,style:const TextStyle(fontSize:25,fontWeight:FontWeight.bold))])));
  Widget _task(dynamic t)=>Card(child:ListTile(leading:const Icon(Icons.task_alt),title:Text(t['subject']?.toString()??'Task'),subtitle:Text((t['name']??'').toString()+' · '+(t['status']??'Unknown').toString()),trailing:Text(t['priority']?.toString()??'')));
  Widget _feedCard(dynamic p)=>Card(child:ListTile(leading:const CircleAvatar(child:Icon(Icons.person)),title:Text(p['employee_name']?.toString()??p['owner']?.toString()??'Employee'),subtitle:Text((p['post_type']??'Update').toString()+'\n'+(p['content']??'').toString()),isThreeLine:true));
}
