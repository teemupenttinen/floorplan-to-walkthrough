using UnrealBuildTool;

public class WalkthroughEditorTarget : TargetRules
{
	public WalkthroughEditorTarget(TargetInfo Target) : base(Target)
	{
		Type = TargetType.Editor;
		DefaultBuildSettings = BuildSettingsVersion.Latest;
		IncludeOrderVersion = EngineIncludeOrderVersion.Latest;
		ExtraModuleNames.Add("Walkthrough");
	}
}
