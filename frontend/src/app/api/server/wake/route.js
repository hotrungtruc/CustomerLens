import { EC2Client, StartInstancesCommand } from "@aws-sdk/client-ec2";

const ec2 = new EC2Client({
  region: process.env.AWS_REGION_NAME || "ap-southeast-2",
  credentials: {
    accessKeyId: process.env.AWS_ACCESS_KEY_ID_CONF,
    secretAccessKey: process.env.AWS_SECRET_ACCESS_KEY_CONF,
  },
});

export async function POST() {
  try {
    const command = new StartInstancesCommand({
      InstanceIds: [process.env.EC2_INSTANCE_ID],
    });
    await ec2.send(command);
    
    return Response.json({
      success: true,
      message: "Đang gửi lệnh kích hoạt máy chủ AWS EC2...",
    });
  } catch (error) {
    return Response.json({ success: false, error: error.message }, { status: 500 });
  }
}
